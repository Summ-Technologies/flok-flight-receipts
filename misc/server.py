# flask_ngrok_example.py
from flask import Flask, request

app = Flask(__name__)

@app.route("/")
def hello():
    return "Bye World!"

@app.route("/emails", methods=['POST'])
def emails():
    pass
    
if __name__ == '__main__':
    app.run(debug=True)
