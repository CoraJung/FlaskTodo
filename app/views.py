from app import app
from flask import render_template, request, redirect, jsonify, make_response, send_from_directory, abort, url_for, flash
from datetime import datetime
import os, shutil
from werkzeug.utils import secure_filename
from PIE.image_properties import analyze_single_image
import numpy as np
import boto3
from uuid import uuid4
from botocore.exceptions import ClientError, WaiterError
from botocore.client import Config
from boto3.s3.transfer import TransferConfig
import botocore

@app.template_filter("clean_date")
def clean_date(dt):
    return dt.strftime("%d %b %Y")

@app.route("/")
def index():

    print(f"Flask ENV is set to: {app.config['ENV']}")
    return render_template("public/upload_image.html")

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

@app.route("/about")
def about():
    return "<h1>About!</h1>"

@app.route("/colony_recognition", methods=["GET", "POST"])
def colony_recognition():
    return render_template("public/colony_recognition.html")


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

    #upload the file to s3
    s3_client = boto3.client('s3', aws_access_key_id=app.config["AWS_ACCESS_KEY_ID"],
                    aws_secret_access_key=app.config["AWS_SECRET_ACCESS_KEY"])

    s3_resource = boto3.resource('s3')
    
    success = False
    """
    # check if bucket is there
    try:
        bucket = s3_resource.Bucket(bucket)
    except ClientError as e:
        bucket = None
    print("bucket name is : ", bucket)
    
    # create bucket object (resource representing s3 object)
    try:
        s3_obj = bucket.Object(object_name)
    except ClientError:
        s3_obj = None
    """

    # upload the file to the bucket
    try:
        # create a unique user directory where all of the files are to be placed
        unique_key = str(uuid4())
        object_name = unique_key + "/" + object_name

        mb = 1024 ** 2
        config = TransferConfig(multipart_threshold=30*mb)
        s3_client.upload_file(file_name, bucket, object_name, Config=config)

    except ClientError as e:
        logging.error(e)
        # then success is still false
    else:
        head = s3_client.head_object(Bucket=bucket, Key=object_name)
        success = head['ContentLength']

    return success


@app.route("/upload-image", methods=["GET", "POST"])
def upload_image():

    if request.method == "POST":

        if request.files:

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
                for file in files:
                    filename = secure_filename(file.filename)
                    save_path = os.path.join(app.config["IMAGE_UPLOADS"], filename)
                    file.save(save_path)

                    print("save_path is: ", save_path)
                    print("filename is: ", filename)

                    filename, file_extension = os.path.splitext(filename)

                    # upload original input file to S3 & granting public access to s3
                    date = datetime.utcnow()
                    date = date.strftime("%Y-%m-%d-%H%MZ")
                    
                    filename = filename + "_" + date + file_extension
                    print("filename is: ", filename)

                    # input file upload to s3
                    success = upload_file_s3(file_name=save_path, bucket="pie-data", object_name=filename)
                    print("success is: ", success)

                    # run analysis and store the processed file to S3
                    process_file(input_src=save_path, object_name=filename)

                    # remove input file from server
                    os.remove(save_path)
                    print("file removed from the server")

                    # create url for individual user folder (UU ID)
                    #return redirect(url_for('get_image', filename=filename))

                    return redirect(url_for('get_image', filename=filename))

                flash("File(s) successfully uploaded")

            print("Image saved")

            return redirect(request.url)

    return render_template("public/upload_image.html")

# def move_file(source, destination):
#     files = os.listdir(source)
#     for file in files:
#         shutil.move(os.path.join(source, file), os.path.join(destination, file))

def process_file(input_src, object_name):

    # locate files
    output_dst = app.config["CLIENT_IMAGES"] # /Users/hyunjung/Projects/FlaskProject/app/static/client/img
    # input_dst = '/Users/hyunjung/MATLAB-Drive/simple_code_test_ims'
    # move_file(input_src, input_dst)

    colony_mask, colony_property_df = analyze_single_image(
        hole_fill_area=np.inf, cleanup=False, max_proportion_exposed_edge=0.75,
        save_extra_info=True, image_type="brightfield", input_im_path=input_src, output_path=output_dst)

    # upload processed files stored in the server to s3 bucket

    for output_folder in os.listdir(output_dst):
        output_folder = os.path.join(app.config["CLIENT_IMAGES"], output_folder)
        print("output file is : ", output_folder)
        
        if len(output_folder) != 0:
            output_files = os.listdir(output_folder)
            for output_file in output_files:
                success = upload_file_s3(output_file, "pie-data", object_name)
                print("upload success: ", object_name)

        else: pass

        # upload file to s3 
        success = upload_file_s3(output_file, "pie-data", output_file)
        print("success is : ", success)

        if success != False:
            print("file successfully uploaded to s3")
            os.remove(output_file)
        else:
            abort(404)

    # move output file
    # output_src = '/Users/hyunjung/MATLAB-Drive/simple_code_test_ims_output/boundary_ims'
    # output_dst = app.config["CLIENT_IMAGES"]
    # move_file(output_src, output_dst)

@app.route("/get-image")

def get_image(filename):
    url = "https://s3.ap-northeast-2.amazonaws.com/" + filename
    date = datetime.utcnow()
    #folder_name = 
    #final_file_name = 
    
    return send_from_directory(
        url,
        filename=filename,
        as_attachment=True
    )
    
    # except FileNotFoundError:
    #     abort(404)

@app.route("/get-csv/<filename>")
def get_csv(filename):

    try:
        return send_from_directory(app.config["CLIENT_CSV"], filename=filename, as_attachment=True
        )
    
    except FileNotFoundError:
        abort(404)
