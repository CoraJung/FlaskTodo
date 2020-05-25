from app import app
from flask import render_template, request, redirect, jsonify, make_response, send_from_directory, abort, url_for, flash
from datetime import datetime
import os, shutil
from werkzeug.utils import secure_filename
from PIE.image_properties import read_and_run_analysis
import numpy as np
import boto3

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


@app.route("/upload-image", methods=["GET", "POST"])

def upload_file_s3(file_name, bucket, object_name=None):
    if object_name is None:
        object_name = file_name

    #upload the file to s3
    config = Config(signature_version=botocore.UNSIGNED)
    s3_client = boto3.client('s3', config=config)
    s3_resource = boto3.resource('s3')
    
    success = False
    
    # check if bucket is created OK
    try:
        bucket = s3_resource.Bucket(bucket)
    except ClientError as e:
        bucket = None

    # Check if client is created OK, and if not etag(file ID) set to be empty
    try:
        head = s3_client.head_object(Bucket= bucket, Key=object_name)
    except ClientError:
        etag=''
    else:
        etag = head['ETag'].strip('"')

    # create bucket object (resource representing s3 object)
    try:
        s3_obj = bucket.Object(filename)
    except ClientError, AttributeError:
        s3_obj = None

    # upload the file to the bucket
    try:
        s3_obj.upload_fileobj(file_name)
    except ClientError, AttributeError:
        pass # then success is still false
    else:
        try:
            # return the object only if its entity tag(etag) is different from the one specificed, otw return 304
            s3_obj.wait_until_exists(IfNoneMatch=etag) 
        except WaiterError as e:
            logging.error(e)
        else:
            head = s3_client.head_object(Bucket=bucket, Key=file_name)
            success = head['ContentLength']

    return success

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

                    # upload input file to S3 & granting public access to s3
                    upload_file_s3(save_path, "pie-data", filename, ExtraArgs={'ACL': 'public-read'})

                    # run analysis and store the processed file to S3
                    process_file(input_src=save_path)

                    # remove input file from server
                    os.remove(save_path)
                    print("file removed from the server")

                    return redirect(url_for('get_image', filename=filename))

                flash("File(s) successfully uploaded")

            print("Image saved")

            return redirect(request.url)

    return render_template("public/upload_image.html")


# def move_file(source, destination):
#     files = os.listdir(source)
#     for file in files:
#         shutil.move(os.path.join(source, file), os.path.join(destination, file))


def process_file(input_src):

    # locate files
    output_dst = app.config["CLIENT_IMAGES"] # /Users/hyunjung/Projects/FlaskProject/app/static/client/img
    # input_dst = '/Users/hyunjung/MATLAB-Drive/simple_code_test_ims'
    # move_file(input_src, input_dst)

    colony_mask, colony_property_df = read_and_run_analysis(
        hole_fill_area=np.inf, cleanup=False, max_proportion_exposed_edge=0.75,
        save_extra_info=False, image_type="brightfield", input_im_path=input_src, output_path=output_dst)

    # upload processed files to s3 bucket
    for output_file in os.listdir(output_dst):
        output_file = os.path.join(app.config["CLIENT_IMAGES"], output_file)

        # upload file to s3 
        success = upload_file_s3(output_file, "pie-data")
        if success != False:
            os.remove(output_file)
            print("file successfully uploaded to s3")
        else:
            abort(404)

    # move output file
    # output_src = '/Users/hyunjung/MATLAB-Drive/simple_code_test_ims_output/boundary_ims'
    # output_dst = app.config["CLIENT_IMAGES"]
    # move_file(output_src, output_dst)

@app.route("/get-image/<filename>")

def get_image(filename):

    try:
        url = "https://s3.ap-northeast-2.amazonaws.com/"

        return send_from_directory(
            url,
            filename=filename,
            as_attachment=True
        )
    
    except FileNotFoundError:
        abort(404)

@app.route("/get-csv/<filename>")
def get_csv(filename):

    try:
        return send_from_directory(app.config["CLIENT_CSV"], filename=filename, as_attachment=True
        )
    
    except FileNotFoundError:
        abort(404)
