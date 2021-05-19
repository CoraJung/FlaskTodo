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
from itertools import product
import botocore
import pandas as pd
import shutil
import time

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

def make_io_dirs(analysis_code, unique_key):
    # create and return input/output directories
    input_path = \
        os.path.join(
            app.config["IMAGE_UPLOADS"],
            str(analysis_code),
            unique_key
            )
    output_path = \
        os.path.join(
            app.config["CLIENT_IMAGES"],
            str(analysis_code)+"_processed",
            unique_key
            )
    if not os.path.exists(input_path):
        os.makedirs(input_path)
    if not os.path.exists(output_path):
        os.makedirs(output_path)
    return(input_path, output_path)

def save_data(review_permission, analysis_code, input_path, output_path, user_email):
    # if review_permission is true, copies input and output path into 
    # folder for data to be kept
    # otherwise deletes intput and output paths
    if review_permission:
        keepdir_in = \
            os.path.join(
                app.config["KEEPDIR_IN"],
                str(analysis_code)
                )
        keepdir_out = \
            os.path.join(
                app.config["KEEPDIR_OUT"],
                str(analysis_code)
                )
        if not os.path.exists(keepdir_in):
            os.makedirs(keepdir_in)
        if not os.path.exists(keepdir_out):
            os.makedirs(keepdir_out)
        keepdir_in_full = shutil.move(input_path, keepdir_in)
        keepdir_out_full = shutil.move(output_path, keepdir_out)
        # if user_email isn't empty, write file with it to both in and 
        # out directories
        if user_email != "":
            for folder in [keepdir_in_full, keepdir_out_full]:
                email_file_path = os.path.join(folder, 'user_email.txt')
                with open(email_file_path, "w") as email_file:
                    email_file.write(str(user_email))
    else:
        shutil.rmtree(input_path)
        shutil.rmtree(output_path)

def upload_to_s3_bucket(file_path, key_name, s3_client, bucket):
    # upload the file to the bucket
    try:
        mb = 1024 ** 2
        config = TransferConfig(multipart_threshold=30*mb)
        s3_client.upload_file(file_path, bucket, key_name, Config=config, ExtraArgs={'ACL': 'public-read'})
    except ClientError as e:
        logging.error(e)
        # then success is still false
    else:
        head = s3_client.head_object(Bucket=bucket, Key=key_name)
        success = head['ContentLength']
#    print(f"original input file {file_path} is uploaded : ", success) #  if it's not False but some number, then upload successful
    return(success)

def zip_analysis_folder(zipname, path):
    now = datetime.now()
    dt_string = now.strftime("%Y-%m-%d_%H_%M_%S")
    out_zip_filename = f"{zipname}_{dt_string}"
    # initially put zip file in a temporary folder outside path, 
    # then move into path, or you get nesting of zip files
    unique_key = str(uuid4())
    temp_zip_location = os.path.join(os.path.dirname(path),unique_key)
    os.makedirs(temp_zip_location)
    # zip file
    out_zip_path_initial = os.path.join(temp_zip_location,out_zip_filename)
    shutil.make_archive(out_zip_path_initial, 'zip', path)
    # move zipped file
    out_zip_path_final = os.path.join(path,out_zip_filename)
    os.rename(out_zip_path_initial+'.zip',out_zip_path_final+'.zip')
    # clean up directories
    shutil.rmtree(temp_zip_location)
    return(out_zip_path_final+'.zip')

def check_image_processing_params(form_dict):
    """
    Return parameter values related to image processing based on 
    website input
    """
    image_type = form_dict["ImageType"]
    hole_fill_area_str = form_dict["HoleFillArea"]
    if hole_fill_area_str.lower().strip()=='inf':
        hole_fill_area = np.inf
    else:
        hole_fill_area = int(hole_fill_area_str)
    if "CleanUp" in form_dict:
        cleanup = True
        max_proportion_exposed_edge = \
            float(form_dict["MaxProportionExposedEdge"])
    else:
        cleanup = False
        max_proportion_exposed_edge = np.nan
    return(image_type, hole_fill_area, cleanup, max_proportion_exposed_edge)

def check_permission_params(form_dict):
    """
    Return parameter values related to permissions to review images
    """    
    if "ReviewPermission" in form_dict:
        review_permission = True
    else:
        review_permission = False
    user_email = form_dict["UserEmail"]
    return(review_permission, user_email)

def check_growth_params(form_dict):
    """
    Return parameter values related to growth rate analysis
    """    
    growth_window_timepoints = int(form_dict["GrowthWindowTimepoints"])
    timepoint_spacing = int(form_dict["TimepointSpacing"])
    return(growth_window_timepoints, timepoint_spacing)


@app.route("/colony-recognition", methods=["GET", "POST"])
def upload_image_cr():
    # set default values
    save_extra_info=True

    if request.method != "POST":
        return render_template("public/colony_recognition.html")

    result = request.form

    site_output_dict = dict(result.items())

    # get image analysis parameters
    image_type, hole_fill_area, cleanup, max_proportion_exposed_edge = \
        check_image_processing_params(site_output_dict)

    review_permission, user_email = check_permission_params(site_output_dict)

    if not request.files:
        flash("⚠️ Please upload an image file", "error")
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
        # save input image to local folder
        input_path, output_path = make_io_dirs("cr", unique_key)

        for file in files:
            filename = secure_filename(file.filename)
            _, file_extension = os.path.splitext(filename)
            filename = f't1xy1{file_extension}'
            
            save_path = os.path.join(input_path, filename)
            file.save(save_path)

            # run and time analysis 
            analysis_start_time = time.process_time()
            colony_mask, colony_property_df = analyze_single_image(
                input_im_path=save_path, output_path=output_path, image_type=image_type,
                hole_fill_area=hole_fill_area, cleanup=cleanup, max_proportion_exposed_edge=max_proportion_exposed_edge,
                save_extra_info=True)
            analysis_stop_time = time.process_time()
            analysis_time = analysis_stop_time-analysis_start_time
            flash("File(s) successfully analyzed, commencing data upload", "info")

            # get number of detected colonies
            detected_colonies = colony_property_df.index.size
            # create a unique key to attach to original input images when they are first created.
            unique_file_key = str(uuid4())

            # upload input files to s3
            upload_file_s3(bucket="pie-colony-recognition-data", file_type="original", folder_name="cr_processed", path=input_path, unique_key=unique_file_key)
            # upload processed files to s3
            boundary_im_url, website_df, df_dict = upload_file_s3(bucket="pie-colony-recognition-data", file_type="processed", folder_name="cr_processed", path=output_path, unique_key=unique_file_key)
            flash("File(s) successfully uploaded", "info")

            df_to_render = df_dict['colony_properties']

            # delete input-output directories if no permission to keep 
            # them, move them if permission granted
            save_data(review_permission, 'cr', input_path, output_path, user_email)
            return render_template(
                "public/render_image.html",
                boundary_im_url=boundary_im_url,
                website_df=website_df,
                analysis_time=round(analysis_time,1),
                detected_colonies = detected_colonies,
                col_prop_tables=[df_to_render.round(1).to_html(classes='styled-table', justify = 'center', header=True, index=False)]
                )

#    return render_template("public/colony_recognition.html")

@app.route('/growth-rate', methods=['GET','POST'])
def upload_image_gr():
    # set default values
    timepoint_spacing = 3600
    growth_window_timepoints = 0

    user_email = ""
    review_permission = False

    if request.method != "POST":
        return render_template("public/growth_rate.html")
    
    result = request.form

    site_output_dict = dict(result.items())

    # get image analysis parameters
    image_type, hole_fill_area, cleanup, max_proportion_exposed_edge = \
        check_image_processing_params(site_output_dict)

    review_permission, user_email = check_permission_params(site_output_dict)

    growth_window_timepoints, timepoint_spacing = \
        check_growth_params(site_output_dict)

    files = request.files.getlist("image")
    print(files)
    total_timepoint_num = len(files)
    print("total_timepoint_num: ", total_timepoint_num)

    # create a unique key to attach to input images when they are first created.
    unique_key = str(uuid4())
    input_path, output_path = make_io_dirs("gr", unique_key)

    print("start uploading files to the local server")
    time_digit_num = np.ceil(np.log10(len(files)+1)).astype(int)
    for i, file in enumerate(files, start=1):
        filename = secure_filename(file.filename)
        _, extension = os.path.splitext(filename)
        print("extension: ", extension)

        print("original filename: ", filename)
        
        timepoint_num = '{:0>{}d}'.format(i, time_digit_num)
        print("formatted timepoint num: ", timepoint_num)
        filename = f't{timepoint_num}xy1{extension}'
        print("new filename: ", filename) # this is so it can work with default function

        save_path = os.path.join(input_path, filename)
        file.save(save_path)
    
    print("run growth rate analysis")
    flash("Analyzing files", "info")
    analysis_start_time = time.process_time()
    run_default_growth_rate_analysis(input_path=input_path, output_path=output_path,
        total_timepoint_num=total_timepoint_num, hole_fill_area=hole_fill_area, cleanup=cleanup,
        max_proportion_exposed_edge=max_proportion_exposed_edge,
        timepoint_spacing=timepoint_spacing, main_channel_imagetype=main_channel_imagetype,
        growth_window_timepoints=growth_window_timepoints, total_xy_position_num=1,
        im_file_extension=extension
        )
    analysis_stop_time = time.process_time()
    analysis_time = analysis_stop_time-analysis_start_time
    flash("File(s) successfully analyzed, commencing data upload", "info")

    # upload input files to s3
    upload_file_s3(bucket="pie-growth-rate-data", file_type="original", folder_name="gr_processed", 
        path=input_path, unique_key=unique_key)
    # upload processed files to s3
    movie_url, website_df, df_dict = upload_file_s3(bucket="pie-growth-rate-data", 
        file_type="processed", folder_name="gr_processed", path=output_path, unique_key=unique_key)
    flash("File(s) successfully uploaded", "info")

    gr_df = df_dict['gr_df']
    col_prop_df = df_dict['colony_properties']

    # get number of colonies
    tracked_colonies = len(col_prop_df.cross_phase_tracking_id.unique())
    growth_colonies = gr_df.index.size

    # delete input-output directories if no permission to keep 
    # them, move them if permission granted
    save_data(review_permission, 'gr', input_path, output_path, user_email)

    return render_template(
        "public/render_image_gr.html",
        movie_url = movie_url,
        website_df=website_df,
        analysis_time = round(analysis_time,1),
        growth_colonies = growth_colonies,
        tracked_colonies = tracked_colonies,
        gr_tables=[gr_df.round(3).to_html(classes='styled-table', justify = 'center', header=True, index=False)])


def upload_file_s3(bucket=None, file_type="original", folder_name="cr_processed", path=None, unique_key=None):
    #file_name = save_path, bucket = "pie-colony-recognition-data" or "pie-growth-rate-data", object_name = unique_filename
    
    # initiate s3 client
    s3_client = boto3.client('s3', aws_access_key_id=app.config["AWS_ACCESS_KEY_ID"],
                    aws_secret_access_key=app.config["AWS_SECRET_ACCESS_KEY"])
#    s3_resource = boto3.resource('s3')

    # upload original input images to s3

    if file_type == "original":
        #decide the filename that will be stored in s3 and upload to s3

        for root, dirs, files in os.walk(path, topdown=True): #path : ~~/gr or ~~/cr
            for filename in files:
                if filename and filename != ".DS_Store":
                    current_name = os.path.join(root, filename)
                    input_filename = filename
                    print(f"-----------input filename: {input_filename}-------------------")
                    object_name = os.path.join(unique_key, "original_input", input_filename) # example: 8ba5c8c0-9edf-4988-8099-d8a249c4d635/original_input/t10xy1.tif
                    print("input filename with unique key attached: ", object_name) 
                    
                    success = upload_to_s3_bucket(current_name, object_name, s3_client, bucket)

    if file_type == "processed":
        print("trying to upload processed files to s3...")
        analysis_folder = os.path.basename(os.path.dirname(path))

        # create pandas df that will hold files to be uploaded
        if analysis_folder=='cr_processed':
            # save directory zip file, mask, boundary_im, and colony csv
            website_df_template = pd.DataFrame(
                {
                    'local_folder':[
                        os.path.basename(path),
                        'single_im_colony_properties',
                        'boundary_ims',
                        'colony_masks'
                        ],
                    'extension':[
                        '.zip',
                        '.csv',
                        '.jpg',
                        '.tif'
                        ],
                    'website_key_general':[
                        'zip file of full directory',
                        'colony property data',
                        'boundary image file',
                        'colony mask file'
                        ]
                    }
                )
        elif analysis_folder=='gr_processed':
            # save directory zip file, growth rate + colony property + 
            # setup file csvs, movie, masks
            website_df_template = pd.DataFrame(
                {
                    'local_folder':[
                        os.path.basename(path),
                        os.path.basename(path),
                        'movies',
                        'colony_masks'
                        ],
                    'extension':[
                        '.zip',
                        '.csv',
                        '.gif',
                        '.tif'
                        ],
                    'website_key_general':[
                        'zip file of full directory',
                        'colony property data',
                        'movie file',
                        'colony mask file'
                        ]
                    }
                )
        # make zipfile of path (output directory)
        if analysis_folder=='gr_processed':
            zipname = 'PIE_growth_analysis_folder'
        elif analysis_folder=='cr_processed':
            zipname = 'PIE_colony_recognition_folder'
        ziped_folder_path = zip_analysis_folder(zipname, path)

        website_df_list = []
        df_dict = {}
        img_url = None
        for root, dirs, files in os.walk(path, topdown=True):
            for filename in files:
                if filename:
                    # initialize success value
                    success = False

                    ### upload all data, but only keep some for website ###
                    # construct the full s3 directory path
                    local_path_ls = root.split(os.path.sep)
                    file_folder = local_path_ls[-1]
                    file_extension = os.path.splitext(filename)[1]

                    # construct the full local path
                    current_name = os.path.join(root, filename)

                    # construct the full s3 directory path
                    folder_index = local_path_ls.index(folder_name) #gr_processed or cr_processed
                    local_path = "/".join(local_path_ls[folder_index:])
                    output_filename = filename
                    object_name = os.path.join(unique_key, local_path, output_filename) #unique_key/gr_processed/.../filename

                    # upload data, including the zip file
                    success = upload_to_s3_bucket(current_name, object_name, s3_client, bucket)

                    # get url for image file and csv file that will be rendered for client
                    region_name = "us-east-2"
                    url_head = f"https://{bucket}.s3.{region_name}.amazonaws.com"
                    url = os.path.join(url_head, object_name)

                    # check whether data needs to be loaded on website
                    if (file_folder, file_extension) in zip(
                        website_df_template.local_folder, website_df_template.extension
                        ):
                        curr_website_df = website_df_template[
                            (website_df_template.local_folder==file_folder) &
                            (website_df_template.extension==file_extension)
                            ].copy()
                        curr_website_df['url'] = url
                        curr_website_df['website_key'] = \
                            f"{curr_website_df.website_key_general.to_list()[0]}: {output_filename}"
                        website_df_list.append(curr_website_df)

                    if folder_name == "gr_processed":

                        if filename=="growth_rates_combined.csv":
                            print("url for client to download: ", url)
                            df_dict['gr_df'] = pd.read_csv(current_name)

                        if filename=="colony_properties_combined.csv":
                            df_dict['colony_properties'] = pd.read_csv(current_name)

                        if "movies" in root:
                            img_url = url
                            print("movie url: ", url)
                    
                    else: #if folder_name == "cr_processed"
                        if "boundary_ims" in root:
                            img_url = url
                        
                        # for csv file that needs to be rendered in table format
                        if "single_im_colony_properties" in root:
                            df_dict['colony_properties'] = pd.read_csv(current_name)

                    if not success:
                        abort(404)

        # after copying everything to website, remove zipped folder
        os.remove(ziped_folder_path)
        
        website_df = pd.merge(website_df_template, pd.concat(website_df_list))

        return img_url, website_df, df_dict









