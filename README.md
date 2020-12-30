# pie-flask
This is a PIE web application using Python Flask framework and AWS S3 storage service. This app is used to demontrate a colony recognition algorithm that takes a single microbial cell growth image and a growth rate analysis algorithm that takes multiple images. The app is deployed on NYU Brooklyn Research Cluster. Make sure [PIE]() is installed in the environment (same directory as where app is). I also didn't include config.py in this repo due to AWS credentials exposure issue, so mkae sure to make one to point to where the client images and processed images are stored.

## 1. Install All Required Dependencies

- `python 3.7`
- `boto3 1.9.66`
- `pandas 1.2.0`
- `numpy 1.19.4`
- `r-uuid 0.1_4`
- `flask 1.1.2`

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
