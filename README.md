# PIE Web Application

This repository contains the implementation for a Flask Web server running PIE Single Colony Recognition. The Web Server uses [flowServ](https://github.com/scailfin/flowserv-core) to run the PIE colony recognition workflow.


## Installation

The app currently has to be installed from GitHub directly. It is recommended that you use a virtual environment for all the following commands. Make sure that [PIE](https://github.com/Siegallab/PIE) is installed in the environment.

```bash

# Install required packages for Flask and flowServ
pip install -r requirements.txt

# Set configuration for flowServ
source app.config

# Create a fresh flowServ database
flowserv init -f

# Install the PIE colony recognition workflow template
flowserv install piesingle -k colony_recognition

# Run the flask server
flask run
```

After running the Flask server the application should be available at [http://127.0.0.1:5000/](http://127.0.0.1:5000/).
