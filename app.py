from flask import Flask
import os
import logging

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "defaultsecretkey")
app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024

logging.basicConfig(level=logging.INFO)

from routes import bp 

app.register_blueprint(bp)  

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5100, debug=False)
