from app import app
from flask import render_template, request, redirect, jsonify, make_response, send_from_directory, abort, url_for, flash
from datetime import datetime
import os
from werkzeug.utils import secure_filename
from PIE.image_properties import analyze_single_image
from PIE.growth_measurement import run_default_growth_rate_analysis
import numpy as np
from uuid import uuid4
from google.cloud import storage
from itertools import product
import pandas as pd
import shutil
import time

# specify temp and long-term storage buckets as global objects
storage_client = storage.Client()
temp_storage_bucket = storage_client.bucket('pie-storage-temp')
long_storage_bucket = storage_client.bucket('pie-storage-long')

@app.route("/")
def index():
    print(f"Flask ENV is set to: {app.config['ENV']}")
    return render_template("public/index.html")


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

def create_dirpath(analysis_code, unique_key, inout, dir_prepend = None):
    """
    Return a path name: analysis_code/unique_key/inout

    analysis_code may be "cr" or "gr"

    unique_key is a unique, uuid-generated key

    inout is either "in", "out", or ""

    dir_prepend is the directory ahead of the returned pathname if not 
    None (default) (e.g. dir_prepend/analysis_code/unique_key/inout)
    """
    if not analysis_code in ["cr","gr"]:
        raise ValueError("analysis_code must be 'cr' or 'gr'")
    if not inout in ["in","out",""]:
        raise ValueError("inout must be 'in' or 'out'")
    if inout=='':
        dirpath = os.path.join(analysis_code, unique_key)
    else:
        dirpath = os.path.join(analysis_code, unique_key, inout)
    if dir_prepend is not None:
        dirpath = os.path.join(dir_prepend, dirpath)
    return(dirpath)

def make_io_dirs(analysis_code, unique_key):
    # create and return input/output directories
    input_path = \
        os.path.join(
            app.config["CLIENT_IMAGES"],
            create_dirpath(analysis_code, unique_key, "in")
            )
    output_path = \
        os.path.join(
            app.config["CLIENT_IMAGES"],
            create_dirpath(analysis_code, unique_key, "out")
            )
    if not os.path.exists(input_path):
        os.makedirs(input_path)
    if not os.path.exists(output_path):
        os.makedirs(output_path)
    return(input_path, output_path)

def dispose_data(review_permission, analysis_code, unique_key, input_path, output_path, user_email, bucket_obj):
    # if review_permission is true, saves input and output paths in 
    # long-term storage bucket
    # deletes input and output paths
    if review_permission:
        # if user_email isn't empty, write file with it to both in and 
        # out directories
        if user_email != "":
            for folder in [input_path, output_path]:
                email_file_path = os.path.join(folder, 'user_email.txt')
                with open(email_file_path, "w") as email_file:
                    email_file.write(str(user_email))
            # prepend user email directory to target pathname to make
            # user-specific folders within cr and gr directories
            dir_prepend = user_email
        else:
            dir_prepend = "unknown_email"
        # upload input and output folders to cluster
        target_in_folder = create_dirpath(
            analysis_code, unique_key, 'in', dir_prepend = dir_prepend
            )
        target_out_folder = create_dirpath(
            analysis_code, unique_key, 'out', dir_prepend = dir_prepend
            )
        upload_folder_to_gcp(input_path, target_in_folder, bucket_obj, make_public=False)
        upload_folder_to_gcp(output_path, target_out_folder, bucket_obj, make_public=False)
    # remove unique dir that contains input and output
    unique_dir_path = os.path.join(
        app.config["CLIENT_IMAGES"],
        create_dirpath(analysis_code, unique_key, "")
        )
    shutil.rmtree(unique_dir_path)

def upload_to_gcp_bucket(bucket_obj, source_file_name, destination_blob_name, public):
    # upload the file to the bucket bucket_obj
    blob = bucket_obj.blob(destination_blob_name)
    blob.upload_from_filename(source_file_name)
    if public:
        blob.make_public()
    success = blob.exists()
    blob_url = blob.public_url
    return(success, blob_url)

def get_within_folder_path(parent_path, full_path):
    """
    Return part of full_path after parent_path
    """
    dir_subpath = full_path.replace(parent_path,'')
    # make into a valid subpath by removing leading slash if necessary
    dir_subpath_split = dir_subpath.split(os.path.sep)
    if len(dir_subpath_split) > 0 and dir_subpath_split[0] == '':
        dir_subpath = os.path.join(*dir_subpath_split[1:])
    return(dir_subpath)

def upload_folder_to_gcp(path_to_upload, target_folder, bucket_obj, make_public):
    """
    Recursively upload all files in path_to_upload to bucket_obj

    path_to_upload is the folder whose inner filetree is to be 
    reproduced inside target_folder in storage;
    NOTE that the folder name of path_to_upload itself will not be 
    reproduced

    bucket_obj is a google.cloud.storage.Client().bucket object of the 
    bucket to which to upload the data

    make_public is whether the folder should be made public

    returns whether uploads of every file in folder were successful
    """
    # upload to cloud
    success_list = []
    path_basename = os.path.basename(path_to_upload)
    for root, dirs, files in os.walk(path_to_upload, topdown=True): #path_to_upload : ~~/gr or ~~/cr
        for filename in files:
            if filename and filename != ".DS_Store":
                current_filepath = os.path.join(root, filename)
                within_dir_path = get_within_folder_path(path_to_upload, current_filepath)
                object_name = os.path.join(target_folder, within_dir_path) # example: 8ba5c8c0-9edf-4988-8099-d8a249c4d635/original_input/t10xy1.tif
                print(f'{current_filepath}->{object_name}')
                success, _ = upload_to_gcp_bucket(bucket_obj, current_filepath, object_name, make_public)
                success_list = success_list+[success]
    # check that success_list is not empty and all values are true
    folder_success = success_list and all(success_list)
    return(folder_success)

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

        file = files[0]
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

        # don't need to upload input files to cloud            
        # upload processed files to cloud
        boundary_im_url, website_df, df_dict = \
            upload_output_files_gc(
                temp_storage_bucket,
                output_path,
                analysis_type_folder_name="cr",
                unique_key=unique_key,
                make_public = True
                )
        flash("File(s) successfully uploaded", "info")

        df_to_render = df_dict['colony_properties']

        # if review_permission is True, copy input and output files to long-term storage 
        # delete input and output folders on computer
        dispose_data(review_permission, 'cr', unique_key, input_path, output_path, user_email, long_storage_bucket)
        return render_template(
            "public/render_image.html",
            boundary_im_url=boundary_im_url,
            website_df=website_df,
            analysis_time=round(analysis_time,1),
            detected_colonies = detected_colonies,
            col_prop_tables=[df_to_render.round(1).to_html(classes='styled-table', justify = 'center', header=True, index=False)]
            )


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
        timepoint_spacing=timepoint_spacing, main_channel_imagetype=image_type,
        growth_window_timepoints=growth_window_timepoints, total_xy_position_num=1,
        im_file_extension=extension
        )
    analysis_stop_time = time.process_time()
    analysis_time = analysis_stop_time-analysis_start_time
    flash("File(s) successfully analyzed, commencing data upload", "info")

    # upload processed files to google cloud
    movie_url, website_df, df_dict = \
        upload_output_files_gc(
                temp_storage_bucket,
                output_path,
                analysis_type_folder_name="gr",
                unique_key=unique_key,
                make_public = True
                )
    flash("File(s) successfully uploaded", "info")

    gr_df = df_dict['gr_df']
    col_prop_df = df_dict['colony_properties']

    # get number of colonies
    tracked_colonies = len(col_prop_df.cross_phase_tracking_id.unique())
    growth_colonies = gr_df.index.size

    # if review_permission is True, copy input and output files to long-term storage 
    # delete input and output folders on computer
    dispose_data(review_permission, 'gr', unique_key, input_path, output_path, user_email, long_storage_bucket)

    return render_template(
        "public/render_image_gr.html",
        movie_url = movie_url,
        website_df=website_df,
        analysis_time = round(analysis_time,1),
        growth_colonies = growth_colonies,
        tracked_colonies = tracked_colonies,
        gr_tables=[gr_df.round(3).to_html(classes='styled-table', justify = 'center', header=True, index=False)])


def upload_output_files_gc(bucket_obj, path_to_upload, analysis_type_folder_name, unique_key, make_public):
    '''
    Uploads all output files in path_to_upload to bucket_obj

    bucket_obj is a google.cloud.storage.Client().bucket object of the 
    bucket to which to upload the data

    path_to_upload is the path whose files will all be uploaded to 
    bucket_obj

    analysis_type_folder_name is either 'gr' (for growth rate) 
    or 'cr' (for colony recognition)

    unique_key is the unique key used for the current user's folder name

    make_public is whether the folder should be made available to access 
    online
    '''
    
    # create pandas df that will hold files to be uploaded
    if analysis_type_folder_name=='cr':
        # save directory zip file, mask, boundary_im, and colony csv
        website_df_template = pd.DataFrame(
            {
                'local_folder':[
                    os.path.basename(path_to_upload),
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
    elif analysis_type_folder_name=='gr':
        # save directory zip file, growth rate + colony property + 
        # setup file csvs, movie, masks
        website_df_template = pd.DataFrame(
            {
                'local_folder':[
                    os.path.basename(path_to_upload),
                    os.path.basename(path_to_upload),
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
    # make zipfile of path_to_upload (output directory)
    if analysis_type_folder_name=='gr':
        zipname = 'PIE_growth_analysis_folder'
    elif analysis_type_folder_name=='cr':
        zipname = 'PIE_colony_recognition_folder'
    zipped_folder_path = zip_analysis_folder(zipname, path_to_upload)

    website_df_list = []
    df_dict = {}
    img_url = None
    for root, dirs, files in os.walk(path_to_upload, topdown=True):
        for filename in files:
            if filename:
                # initialize success value
                success = False

                ### upload all data, but only keep some for website ###
                # construct the full local path
                current_filepath = os.path.join(root, filename)
                # get the file's extension and the folder it's in
                local_path_ls = root.split(os.path.sep)
                file_folder = os.path.basename(root)
                file_extension = os.path.splitext(filename)[1]
                # construct the full online directory path
                folder_index = local_path_ls.index(analysis_type_folder_name) #gr or cr
                local_path = os.path.join(*local_path_ls[folder_index:])
                output_filename = filename
                object_name = os.path.join(analysis_type_folder_name, unique_key, local_path, output_filename) #gr/unique_key/.../filename

                # upload data, including the zip file
                success, url = upload_to_gcp_bucket(bucket_obj, current_filepath, object_name, make_public)

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

                if analysis_type_folder_name == "gr":

                    if filename=="growth_rates_combined.csv":
                        print("url for client to download: ", url)
                        df_dict['gr_df'] = pd.read_csv(current_filepath)

                    if filename=="colony_properties_combined.csv":
                        df_dict['colony_properties'] = pd.read_csv(current_filepath)

                    if file_folder == "movies":
                        img_url = url
                        print("movie url: ", url)
                
                else: #if analysis_type_folder_name == "cr"
                    if file_folder == "boundary_ims":
                        img_url = url
                    
                    # for csv file that needs to be rendered in table format
                    if file_folder == "single_im_colony_properties":
                        df_dict['colony_properties'] = pd.read_csv(current_filepath)

                if not success:
                    abort(404)

    # after copying everything to website, remove zipped folder
    os.remove(zipped_folder_path)
    
    website_df = pd.merge(website_df_template, pd.concat(website_df_list))

    return img_url, website_df, df_dict








