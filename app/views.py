from app import app
from flask import render_template, request, redirect, jsonify, make_response, send_from_directory, abort, url_for, flash
from datetime import datetime
import os
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

    # return render_template("public/jinja.html", my_name=my_name, age=age, langs=langs, freinds=friends, 
    #                                             colors=colors, cool=cool, GitRemote=GitRemote, repeat=repeat, 
    #                                             my_remote=my_remote, date=date, my_html=my_html, suspicious=suspicious
    #                                             )


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


def make_file_name(filename):
    # create a unique user directory where all of the files are to be placed
    unique_key = str(uuid4())
    object_name = unique_key + "/" + object_name


@app.route("/colony-recognition", methods=["GET", "POST"])

def upload_image_cr():
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
        return render_template("public/colony_recognition.html")

    if not request.files:
        return render_template("public/colony_recognition.html")

    if not allowed_image_filesize(request.cookies.get("filesize")):
        flash("⚠️ File exceeded maximum size", "error")
        return redirect(request.url)

    image = request.files["image"]

    if image.filename == "":
        flash("⚠️ Please upload an image file", "error")
        return redirect(request.url)
    
    if not allowed_image(image.filename):
        flash("⚠️ Image extension not allowed", "error")
        return redirect(request.url)
    
    else:
        files = request.files.getlist("image")
        print("number of files uploaded: ", len(files)) # should be just 1
        if len(files) != 1:
            flash("⚠️ Upload a single image file only", "error")
            return redirect(request.url)
        # create a unique key to attach to original input image when it was first created.
        unique_key = str(uuid4())

        for file in files:
            filename = secure_filename(file.filename)
            _, file_extension = os.path.splitext(filename)
            filename = f't1xy1.{file_extension}'
            
            # save input image to local folder
            save_path = os.path.join(app.config["IMAGE_UPLOADS"], "cr", filename)
            file.save(save_path)

            input_path = os.path.join(app.config["IMAGE_UPLOADS"], "cr")
            output_path = os.path.join(app.config["CLIENT_IMAGES"], "cr_processed") # /Users/hyunjung/Projects/FlaskProject/app/static/client/img/cr_processed
            # run analysis 
            colony_mask, colony_property_df = analyze_single_image(
                hole_fill_area=hole_fill_area, cleanup=cleanup, max_proportion_exposed_edge=max_proportion_exposed_edge,
                save_extra_info=True, image_type=image_type, input_im_path=save_path, output_path=output_path)
            flash("File(s) successfully analyzed", "info")

            # create a unique key to attach to original input images when they are first created.
            unique_key = str(uuid4())
            date = datetime.utcnow()
            date = date.strftime("%Y-%m-%d-%H%MZ")

            # upload input files to s3
            upload_file_s3(bucket="pie-colony-recognition-data", file_type="original", folder_name="cr_processed", path=input_path, unique_key=unique_key, date=date)
            # upload processed files to s3
            boundary_im_url, url_ls, df_to_render = upload_file_s3(bucket="pie-colony-recognition-data", file_type="processed", folder_name="cr_processed", path=output_path, unique_key=unique_key, date=date)
            flash("File(s) successfully uploaded", "info")

            return render_template("public/render_image.html", boundary_im_url=boundary_im_url, url_ls=url_ls, column_names=df_to_render.columns.values,
                                    row_data=list(df_to_render.values.tolist()), zip=zip)                

    return render_template("public/colony_recognition.html")

@app.route('/growth-rate', methods=['GET','POST'])
def upload_image_gr():
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
    for i, file in enumerate(files, start=1):
        filename = secure_filename(file.filename)
        _, extension = os.path.splitext(filename)
        print("extension: ", extension)

        print("original filename: ", filename)
        timepoint_num = "{:02}".format(i)
        print("formatted timepoint num: ", timepoint_num)
        filename = f't{timepoint_num}xy1{extension}'
        print("new filename: ", filename) # this is so it can work with default function

        save_path = os.path.join(app.config["IMAGE_UPLOADS"], "gr", filename)
        file.save(save_path)
    
    input_path = os.path.join(app.config["IMAGE_UPLOADS"], "gr")
    ouput_path = os.path.join(app.config["CLIENT_IMAGES"], "gr_processed")

    print("run growth rate analysis")
    run_default_growth_rate_analysis(input_path=input_path, output_path=ouput_path,
        total_timepoint_num=total_timepoint_num, hole_fill_area=hole_fill_area, cleanup=cleanup,
        max_proportion_exposed_edge=max_proportion_exposed_edge, minimum_growth_time=minimum_growth_time,
        timepoint_spacing=timepoint_spacing, main_channel_imagetype=main_channel_imagetype,
        growth_window_timepoints=growth_window_timepoints, total_xy_position_num=4
        )

    # create a unique key to attach to original input images when they are first created.
    unique_key = str(uuid4())
    date = datetime.utcnow()
    date = date.strftime("%Y-%m-%d-%H%MZ")
    # upload input files to s3
    upload_file_s3(bucket="pie-growth-rate-data", file_type="original", folder_name="gr_processed", 
        path=input_path, unique_key=unique_key, date=date)
    # upload processed files to s3
    boundary_ims_url_ls, url_ls, dfs_to_render_ls, movie_url = upload_file_s3(bucket="pie-growth-rate-data", 
        file_type="processed", folder_name="gr_processed", path=ouput_path, unique_key=unique_key, date=date)

    return render_template("public/render_image_gr.html", boundary_ims_url_ls=boundary_ims_url_ls, url_ls=url_ls, column_names_grcombined=dfs_to_render_ls[0].columns.values,
                                                        column_names_cpcombined=dfs_to_render_ls[1].columns.values, row_data_grcombined=list(dfs_to_render_ls[0].values.tolist()), 
                                                        row_data_cpcombined=list(dfs_to_render_ls[1].values.tolist()), movie_url=movie_url, zip=zip)
    

def upload_file_s3(bucket=None, file_type="original", folder_name="cr_processed", path=None, unique_key=None, date=None):
    #file_name = save_path, bucket = "pie-colony-recognition-data" or "pie-growth-rate-data", object_name = unique_filename
    
    # initiate s3 client
    s3_client = boto3.client('s3', aws_access_key_id=app.config["AWS_ACCESS_KEY_ID"],
                    aws_secret_access_key=app.config["AWS_SECRET_ACCESS_KEY"])
    s3_resource = boto3.resource('s3')
    success = False

    url_ls = []
    boundary_ims_url_ls = []
    dfs_to_render_ls = []
    # upload original input images to s3

    if file_type == "original":
        #decide the filename that will be stored in s3 and upload to s3

        for root, dirs, files in os.walk(path, topdown=True): #path : ~~/gr or ~~/cr
            for filename in files:
                if filename and filename != ".DS_Store":
                    current_name = os.path.join(root, filename)
                    
                    print(f"-----------filename: {filename}-------------------")
                    input_filename, file_extension = os.path.splitext(filename)
                    print(f"-----------input filename: {input_filename}-------------------")
                    input_filename = input_filename + "_" + date + file_extension
                    print(f"-----------updated input filename: {input_filename}-------------------")
                    object_name = os.path.join(unique_key, "original_input_file(s)", input_filename) # example: 8ba5c8c0-9edf-4988-8099-d8a249c4d635/original_input_file(s)/t10xy4_2020-12-23-0337Z.tif
                    print("input filename with unique key and date attached: ", object_name) 
                    
                    # upload the file to the bucket
                    try:
                        mb = 1024 ** 2
                        config = TransferConfig(multipart_threshold=30*mb)
                        s3_client.upload_file(current_name, bucket, object_name, Config=config, ExtraArgs={'ACL': 'public-read'})

                    except ClientError as e:
                        logging.error(e)
                        # then success is still false
                    else:
                        head = s3_client.head_object(Bucket=bucket, Key=object_name)
                        success = head['ContentLength']

                    print(f"original input file {filename} is uploaded : ", success) #  if it's not False but some number, then upload successful 
                    os.remove(current_name)
                    print(f"original input file {filename} is deleted from local server")


    if file_type == "processed":
        print("trying to upload processed files to s3...")
        for root, dirs, files in os.walk(path, topdown=True):
            for filename in files:
                if filename and filename != ".DS_Store":
                    # construct the full local path
                    current_name = os.path.join(root, filename)
                    
                    # construct the full s3 directory path
                    local_path_ls = root.split(os.path.sep)
                    print("local path ls :", local_path_ls)
                    folder_index = local_path_ls.index(folder_name) #gr_processed or cr_processed
                    local_path = "/".join(local_path_ls[folder_index:])

                    output_filename, file_extension = os.path.splitext(filename)
                    output_filename = output_filename + "_" + date + file_extension

                    object_name = os.path.join(unique_key, local_path, output_filename) #unique_key/gr_processed/.../filename
                    
                    # upload the file to the bucket
                    try:
                        mb = 1024 ** 2
                        config = TransferConfig(multipart_threshold=30*mb)
                        s3_client.upload_file(current_name, bucket, object_name, Config=config, ExtraArgs={'ACL': 'public-read'})

                    except ClientError as e:
                        logging.error(e)
                        # then success is still false
                    else:
                        head = s3_client.head_object(Bucket=bucket, Key=object_name)
                        success = head['ContentLength']

                    print(f"processed file {filename} is uploaded : ", success) #  if it's not False but some number, then upload successful 

                    # get url for image file and csv file that will be rendered for client
                    region_name = "us-east-2"
                    url_head = f"https://{bucket}.s3.{region_name}.amazonaws.com"
                    url = os.path.join(url_head, object_name)

                    if folder_name == "gr_processed":
                        download_csv_ls = ['growth_rates_combined.csv', 'colony_properties_combined.csv']
                        if filename in download_csv_ls:
                            print("url for client to download: ", url)
                            url_ls.append(url)
                            dfs_to_render_ls.append(pd.read_csv(current_name))

                        if "boundary_ims" in root:
                            print("boundary ims url: ", url)
                            boundary_ims_url_ls.append(url)

                        if "movies" in root:
                            movie_url = url
                            print("movie url: ", url)
                    
                    else: #if folder_name == "cr_processed"
                        url_ls.append(url)
                        if "boundary_ims" in root:
                            boundary_im_url = url
                        
                        # for csv file that needs to be rendered in table format
                        if "single_im_colony_properties" in root:
                            df_to_render = pd.read_csv(current_name)
                    
                    if success:
                        os.remove(current_name)
                        print(f"processed file {filename} is deleted from local server")
                    else:
                        abort(404)

        if folder_name == "gr_processed":
            url_ls = url_ls + boundary_ims_url_ls
            boundary_ims_url_ls.sort()

            return boundary_ims_url_ls, url_ls, dfs_to_render_ls, movie_url

        else:
            return boundary_im_url, url_ls, df_to_render









