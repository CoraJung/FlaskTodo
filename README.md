# pie-flask
This is a PIE web application using Python Flask framework and AWS S3 storage service. You can take a look at the app by visiting [here](http://128.122.217.86/) with NYU VPN on.
This app is used to demontrate a colony recognition algorithm that takes a single microbial cell growth image and a growth rate analysis algorithm that takes multiple images. The app is deployed on NYU Brooklyn Research Cluster. Make sure [PIE]() is installed in the environment (same directory as where app is). I also didn't include config.py in this repo due to AWS credentials exposure issue, so make sure to make one to point to where the client images and processed images are stored.

## 1. Install All Required Dependencies

```
python 3.7
boto3 1.9.66
pandas 1.2.0
numpy 1.19.4
r-uuid 0.1_4
flask 1.1.2
```

## 2. Start Web Server 
I recommend running it under development environment first, so you can find any possible bugs.

```
export FLASK_APP=run.py
export FLASK_ENV=development 
flask run
```

If app is successfully running, then you can simply go to the url.
`http://<IP>:5000`
If you run it locally, the app should be running at http://127.0.0.1:5000/

# General Workflow
### 1. Upload images
First, client uploads a single image (colony recognition page - `upload_image_cr()`) or multiple images (growth rate analysis - `upload_image_gr()`).
The default parameters are set as:

**Colony Recognition**
```
hole_fill_area=np.inf
cleanup=False
max_proportion_exposed_edge=0.25
save_extra_info=True
image_type="brightfield"
```

**Growth Rate**
```
total_timepoint_num = 1
hole_fill_area = np.inf
cleanup = False
max_proportion_exposed_edge = 0.75
minimum_growth_time = 4
timepoint_spacing = 3600
main_channel_imagetype = 'brightfield'
growth_window_timepoints = 0  
```

### 2. File verification
The app receives POST request, then it goes through series of verficiations such as filesize, file extensions, file existence, etc.

### 3. Image analysis
The image(s) is saved in the server first, and then the `analyze_single_image()` or `run_default_growth_rate_analysis()` processes the saved input image(s), depending on which analysis the client chooses.

### 4. AWS S3 Upload 
The processed images and other result files are saved locally first, and then uploaded to AWS S3 bucket using `upload_file_s3()` function, where you need to specify a few parameters

```
bucket=<s3 bucket name where you want to upload the images>
file_type=<the type of files. "processed" if it's processed files or "original" if it's input image file(s)>
folder_name=<"gr_processed" if it's growth rate analysis or "cr_processed" if it's colony recognition analysis>
path=<path to files>
unique_key=<unique_key to be assigned to each client>
date=<date>    
```
  
### 5. File removal in the local server
After images and files are uploaded to S3, the files in the local server are removed.

### 6. Results for the clients
The client can see the results of the analysis in the new page (either `render_image.html` or `render_image_gr.html`), and will be given the urls to S3 bucket to download the processed files.

