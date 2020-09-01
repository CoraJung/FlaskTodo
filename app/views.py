from app import app
from flask import render_template, request, redirect, jsonify, make_response, send_from_directory, abort, url_for, flash
from datetime import datetime
import os, shutil
from werkzeug.utils import secure_filename
from PIE.image_properties import analyze_single_image
from PIE.growth_measurement import run_default_growth_rate_analysis
import numpy as np
import boto3
from uuid import uuid4
from botocore.exceptions import ClientError, WaiterError
from botocore.client import Config
from boto3.s3.transfer import TransferConfig
import botocore
import re
import pandas as pd

@app.template_filter("clean_date")
def clean_date(dt):
    return dt.strftime("%d %b %Y")

@app.route("/")
def index():

    print(f"Flask ENV is set to: {app.config['ENV']}")
    return render_template("public/index.html")

@app.route("/jinja")
def jinja():

    my_name = "Cora"
    
    age = 28

    langs = ["Python", "JavaScript", "Bash", "C", "Ruby"]

    friends = {
        "Tom":30,
        "Amy":40,
        "Tony":40,
        "Clarissa":50
    }

    colors = ("Red", "Blue")

    cool = True

    class GitRemote:
        def __init__(self, name, description, url):
            self.name = name
            self.description = description
            self.url = url

        def pull(self):
            return f"Pulling repo {self.name}"

        def clone(self):
            return f"Cloning into {self.url}"

    my_remote = GitRemote(name='Flask Jinja', description='Template Design Tutorial', url='https://github.com/CoraJung/Jinja.git')

    def repeat(x, qty):
        return x * qty

    date = datetime.utcnow()

    my_html = "<h1>This Is Some HTML</h1>"

    suspicious = "<script>alert('You Got Hacked')</script>"

    return render_template("public/jinja.html", my_name=my_name, age=age, langs=langs, freinds=friends, 
                                                colors=colors, cool=cool, GitRemote=GitRemote, repeat=repeat, 
                                                my_remote=my_remote, date=date, my_html=my_html, suspicious=suspicious
                                                )


"""
\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\
    RUN PIE Algo IN FLASK
\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\
"""

def allowed_image(filename):

    if not "." in filename:
        return False
    
    ext = filename.rsplit(".", 1)[1]

    if ext.upper() in app.config["ALLOWED_IMAGE_EXTENSIONS"]:
        return True
    else:
        return False

def allowed_image_filesize(filesize):

    if int(filesize) <= app.config["MAX_CONTENT_LENGTH"]:
        return True
    else:
        return False

# upload file to s3 bucket
# file name = local path where the input file is located
# bucket = bucket name ("pie-data")
# object_name = secure file name (filename + date)

def make_file_name(filename):
    # create a unique user directory where all of the files are to be placed
    unique_key = str(uuid4())
    object_name = unique_key + "/" + object_name


def upload_file_s3(file_name, bucket, object_name=None):
    if object_name is None:
        object_name = file_name


    unique_key, object_name = object_name.split("_", 1)
    object_name = os.path.join(unique_key, object_name)


    #upload the file to s3
    s3_client = boto3.client('s3', aws_access_key_id=app.config["AWS_ACCESS_KEY_ID"],
                     aws_secret_access_key=app.config["AWS_SECRET_ACCESS_KEY"])


    s3_resource = boto3.resource('s3')
    
    success = False

    # upload the file to the bucket
    try:

        mb = 1024 ** 2
        config = TransferConfig(multipart_threshold=30*mb)
        s3_client.upload_file(file_name, bucket, object_name, Config=config, ExtraArgs={'ACL': 'public-read'})

    except ClientError as e:
        logging.error(e)
        # then success is still false
    else:
        head = s3_client.head_object(Bucket=bucket, Key=object_name)
        success = head['ContentLength']

    return success


@app.route("/upload-image", methods=["GET", "POST"])

def upload_image():

    # set default values
    hole_fill_area=np.inf
    cleanup=False
    max_proportion_exposed_edge=0.25
    save_extra_info=True
    image_type="brightfield"
    user_email = ""
    review_permission = False

    result = request.form

    # set parameters
    for key, value in result.items():
        print(key, value)

        if key == "ImageType" and value == "phasecontrast":
            image_type = value
        
        elif key == "HoleFillArea":
            if value == "inf" or value == "":
                pass
            else:
                hole_fill_area = int(value)
        
        elif key == "MaxProportionExposedEdge" and value != "":
            cleanup = True
            max_proportion_exposed_edge = float(value)
        
        elif key == "UserEmail" and value != "":
            user_email = value
        
        elif key == "Disclaimer":
            review_permission = True

    if request.method != "POST":
        return render_template("public/upload_image.html")

    if not request.files:
        return render_template("public/upload_image.html")

    if not allowed_image_filesize(request.cookies.get("filesize")):
        print("File exceeded maximum size")
        return redirect(request.url)

    image = request.files["image"]

    if image.filename == "":
        print("image must have a filename")
        return redirect(request.url)
    
    if not allowed_image(image.filename):
        print("That image extension is not allowed")
        return redirect(request.url)
    
    else:
        files = request.files.getlist("image")

        # create a unique key to attach to original input image when it was first created.
        unique_key = str(uuid4())

        for file in files:
            filename = secure_filename(file.filename)
            input_filename, file_extension = os.path.splitext(filename)
            
            date = datetime.utcnow()
            date = date.strftime("%Y-%m-%d-%H%MZ")
            
            unique_filename = unique_key + "_" + input_filename + "_" + date + file_extension
            print("filename with unique key and date attached: ", unique_filename)

            # save input image to local folder
            save_path = os.path.join(app.config["IMAGE_UPLOADS"], unique_filename)
            file.save(save_path)

            # upload original input file to S3 & granting public access to s3
            success = upload_file_s3(file_name=save_path, bucket="pie-data", object_name=unique_filename)
            print("success is: ", success)

            # run analysis and store the processed file to S3
            boundary_im_url, url_ls, df = process_file(input_src=save_path, object_name=unique_filename,
                                                        hole_fill_area=hole_fill_area, cleanup=cleanup, max_proportion_exposed_edge=max_proportion_exposed_edge,
                                                        save_extra_info=True, image_type=image_type)
            print(df)

            # remove input file from server
            print("start removing input file")
            os.remove(save_path)
            print("file removed from the server")

            return render_template("public/render_image.html", boundary_im_url=boundary_im_url, url_ls=url_ls, column_names=df.columns.values,
                                    row_data=list(df.values.tolist()), zip=zip)                

        flash("File(s) successfully uploaded")

    print("Image saved")

    #return redirect(request.url)
    # return "OK"

    return render_template("public/upload_image.html")

# def move_file(source, destination):
#     files = os.listdir(source)
#     for file in files:
#         shutil.move(os.path.join(source, file), os.path.join(destination, file))

def process_file(input_src, object_name, 
                hole_fill_area, cleanup, max_proportion_exposed_edge,
                save_extra_info, image_type):

    # locate files
    output_dst = app.config["CLIENT_IMAGES"] # /Users/hyunjung/Projects/FlaskProject/app/static/client/img
    url_ls = []
    df_to_render_csv = None

    colony_mask, colony_property_df = analyze_single_image(
        hole_fill_area=hole_fill_area, cleanup=cleanup, max_proportion_exposed_edge=max_proportion_exposed_edge,
        save_extra_info=True, image_type=image_type, input_im_path=input_src, output_path=output_dst)

    # upload processed files stored in the server to s3 bucket
    # filter out unnecessary dierctories and set them as upload target
    folder_ls = ['single_im_colony_properties', 'colony_center_overlays', 'jpgGRimages', 
                'boundary_ims', 'threshold_plots', 'colony_masks']

    for output_folder in os.listdir(output_dst):
        output_folder_path = os.path.join(app.config["CLIENT_IMAGES"], output_folder)
        print("output folder is : ", output_folder)

        if output_folder in folder_ls:
            output_files = os.listdir(output_folder_path)

            for output_file in output_files:
                print("output_file: ", output_file)
                unique_key, filename = output_file.split("_", 1)

                output_file_final = "_".join([unique_key, output_folder, filename])
                print("output_file_final: ", output_file_final)

                output_file_path = os.path.join(output_folder_path, output_file)
                print("output_file_path: ", output_file_path)

                # threshold_info.csv is the only file that doesn't have unique key and input filename in its filename, so manually extract that informration.
                if output_file == "threshold_info.csv":
                    df = pd.read_csv(output_file_path)
                    input_name = df.columns[0]
                    unique_key = input_name.split("_", 1)[0]
                    filename_dict = re.match(r"(?P<filename>.+)_(?P<date_time>\d{4}-\d{2}-\d{2}-\d{4}Z)$", input_name.split("_", 1)[1]).groupdict()
                    input_filename = filename_dict["filename"]
                    date = filename_dict["date_time"]

                    output_file_final = "_".join([unique_key, output_folder, input_filename, date, output_file])


                success = upload_file_s3(file_name=output_file_path, bucket="pie-data", object_name=output_file_final)

                # get url for image file and csv file that will be rendered for client
                bucket_name = "pie-data"
                region_name = "us-east-2"
                url_head = f"https://{bucket_name}.s3.{region_name}.amazonaws.com"

                unique_key, object_name = output_file_final.split("_", 1)
                object_name = os.path.join(unique_key, object_name)
                url = os.path.join(url_head, object_name)
                url_ls.append(url)
                
                if "boundary_ims" in output_file_final:
                    print("boubdary_ims is in output_file: ", output_file_final)
                    boundary_im_url = url
                
                # for csv file that needs to be rendered in table format
                if "single_im_colony_properties" in output_file_final:
                    df_to_render_csv = pd.read_csv(output_file_path)

                if success:
                    print("file successfully uploaded to s3")
                    os.remove(output_file_path)
                    print("file successfully removed from the server")
                else:
                    abort(404)

        else: pass
    
    return boundary_im_url, url_ls, df_to_render_csv


@app.route('/growth-rate', methods=['GET','POST'])
def growth_rate_upload():
    # if request.method == "POST":
    #     files = flask.request.files.getlist("file")
    #     for file in files:
    #         file.save(os.path.join(app.config['UPLOAD_FOLDER'], file.filename))

    # set default values
    total_timepoint_num = 1
    hole_fill_area = np.inf
    cleanup = False
    max_proportion_exposed_edge = 0.75
    minimum_growth_time = 4
    timepoint_spacing = 3600
    main_channel_imagetype = 'brightfield'
    growth_window_timepoints = 0

    user_email = ""
    review_permission = False

    if request.method != "POST":
        return render_template("public/growth_rate.html")
    
    else:
        result = request.form

        # receive parameters from client
        for key, value in result.items():
            print(key, value)

            if key == "ImageType" and value == "phasecontrast":
                main_channel_imagetype = value
            
            elif key == "HoleFillArea":
                if value == "inf" or value == "":
                    pass
                else:
                    hole_fill_area = int(value)
            
            elif key == "MaxProportionExposedEdge" and value != "":
                cleanup = True
                max_proportion_exposed_edge = float(value)
            
            elif key == "MinimumGrowthTime" and value != "":
                minimum_growth_time = int(value)
            
            elif key == "GrowthWindowTimepoints" and value != "":
                growth_window_timepoints = int(value)

            elif key == "TimepointSpacing" and value != "":
                timepoint_spacing = int(value)
            
            elif key == "UserEmail" and value != "":
                user_email = value
            
            elif key == "Disclaimer":
                review_permission = True

        files = request.files.getlist("image")
        total_timepoint_num = len(files)
        print("total_timepoint_num: ", total_timepoint_num)

        print("start uploading files to the local server")
        for file in files:
            filename = secure_filename(file.filename)
            print(filename)

            # save input image to local folder
            save_path = os.path.join(app.config["IMAGE_UPLOADS"], filename)
            file.save(save_path)

        input_path = app.config["IMAGE_UPLOADS"]
        ouput_path = app.config["CLIENT_IMAGES"]

        print("run growth rate analysis")
        run_default_growth_rate_analysis(input_path=input_path, output_path=ouput_path,
            total_timepoint_num=total_timepoint_num, hole_fill_area=hole_fill_area, cleanup=cleanup,
            max_proportion_exposed_edge=max_proportion_exposed_edge, minimum_growth_time=minimum_growth_time,
            timepoint_spacing=timepoint_spacing, main_channel_imagetype=main_channel_imagetype,
            growth_window_timepoints=growth_window_timepoints, total_xy_position_num=4
            )
    
    return render_template("public/render_image_gr.html")