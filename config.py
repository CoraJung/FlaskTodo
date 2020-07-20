
class Config(object):
    DEBUG = False
    TESTING = False

    SECRET_KEY = "jaja0808"

    DB_NAME = "production-db"
    DB_USERNAME = "root"
    DB_PASSWORD = "example"

    UPLOADS = "/home/username/FLASKPROJECT/app/static/images/uploads"


    IMAGE_UPLOADS = "/Users/hyunjung/Projects/FlaskProject/app/static/img/uploads"
    ALLOWED_IMAGE_EXTENSIONS = ["PNG", "JPG", "JPEG", "GIF", "TIF", "TIFF"]
    MAX_CONTENT_LENGTH = 150 * 1024 * 1024

    SESSION_COOKIE_SECURE = True

    CLIENT_IMAGES = "/Users/hyunjung/Projects/FlaskProject/app/static/client/img"
    CLIENT_CSV = "/Users/hyunjung/Projects/FlaskProject/app/static/client/csv" 
    CLIENT_PDF = "/Users/hyunjung/Projects/FlaskProject/app/static/client/pdf"

class ProductionConfig(Config):
    pass

class DevelopmentConfig(Config):
    DEBUG = True

    DB_NAME = "development-db"
    DB_USERNAME = "root"
    DB_PASSWORD = "example"


    S3_BUCKET_NAME = 'pie-data'
    AWS_ACCESS_KEY_ID = "AKIATBIENWNGAMDRD44C"
    AWS_SECRET_ACCESS_KEY = "m7g+ecQreZJdof9f6o7ROYFG0vXZVTao642au/9/"

    UPLOADS = "/home/username/projects/flask_test/FLASKPROJECT/app/static/images/uploads"
    IMAGE_UPLOADS = "/Users/hyunjung/Projects/FlaskProject/app/static/img/uploads"

    SESSION_COOKIE_SECURE = False

class TestingConfig(Config):
    TESTING = True

    UPLOADS = "/home/username/projects/flask_test/FLASKPROJECT/app/static/images/uploads"

    SESSION_COOKIE_SECURE = False
