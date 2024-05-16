from io import BytesIO
import pandas as pd
import numpy as np  # Added import
import os  # Added import
from collections import Counter
from faker import Faker
import random
import webbrowser
import matplotlib.pyplot as plt
import base64
from flask import Flask, render_template, request, jsonify
import re
from pdfreader import SimplePDFViewer, PDFDocument
import firebase_admin  # Added import
from firebase_admin import credentials, firestore  # Added import

app = Flask(__name__)

# Initialize Firebase Admin SDK
cred = credentials.Certificate("rfpos-a18d7-firebase-adminsdk-wod3i-0456ff7ce6.json")
firebase_admin.initialize_app(cred)
db = firestore.client()

TEMPLATES_DIR = 'templates'

# Retrieve data from Firebase
def retrieve_from_firebase():
    finance_ref = db.collection('finance')
    finance_data = [doc.to_dict() for doc in finance_ref.stream()]
    return finance_data

# Function to create HTML table from data
def create_html_table(data):
    df = pd.DataFrame(data)
    html_table = df.to_html(index=False)

    styled_html = f"""
        <html>
        <head>
        <style>
            body {{
                display: flex;
                align-items: center;
                justify-content: center;
                margin: 0;
                background: white; /* Set background to transparent black (adjust the alpha value as needed) */
                color: black; /* Set text color to white */
            }}
            th, td {{
                text-align: center;
            }}
            table {{
                border-collapse: collapse;
                width: 80%;
            }}
            th, td {{
                border: 1px solid black;
                padding: 8px;
            }}
        </style>
        </head>
        <body>
        {html_table}
        </body>
        </html>
    """

    return styled_html

# Extract information from PDF
def extract_info(pdf_path):
    info = {
        "Name": "",
        "NPV": "",
        "IRR": "",
        "Phone no": "",
        "Time taken": "",
        "Budget": "",
        "Email": "",
        "Number of Previous works": ""
    }

    with open(pdf_path, "rb") as file:
        doc = PDFDocument(file)
        viewer = SimplePDFViewer(file)
        for _ in doc.pages():
            viewer.render()
            page_text = ''.join(viewer.canvas.strings)

            # Updated extraction method with error handling
            try:
                info["Name"] = re.search(r'Name:(\w+)', page_text).group(1)
                info["NPV"] = re.search(r'NPV:(\d+)', page_text).group(1)
                info["IRR"] = re.search(r'IRR:(\d+)', page_text).group(1)
                phone_match = re.search(r'Phone no:(\d+)', page_text)
                info["Phone no"] = phone_match.group(1) if phone_match else ""
                info["Time taken"] = re.search(r'Time taken:(\d+)', page_text).group(1)
                info["Budget"] = re.search(r'Budget:(\d+)', page_text).group(1)
                info["Email"] = re.search(r'Email:\s*([\w\.-]+@[\w\.-]+)', page_text).group(1)
                prev_works_match = re.search(r'Number of Previous works:(\d+)', page_text)
                info["Number of Previous works"] = prev_works_match.group(1) if prev_works_match else ""

            except AttributeError:
                print("Error: Attribute not found in PDF content.")
                # Handle the error here

    return info

# Publish HTML content
def publish_html(html_content):
    file_path = os.path.join(TEMPLATES_DIR, "finance_data.html")

    with open(file_path, "w") as f:
        f.write(html_content)

# Generate budget bar graph
def generate_budget_bar_graph(data):
    names = [entry["Name"] for entry in data]
    budget_values = [entry["Budget"] for entry in data]

    plt.figure(figsize=(12, 6))
    plt.bar(np.arange(len(names)), budget_values)
    plt.title('Budget Values by Name')
    plt.xlabel('Names')
    plt.ylabel('Budget (in lakhs)')
    plt.xticks(np.arange(len(names)), names, rotation=45, ha='right')
    plt.tight_layout()

    buffer = BytesIO()
    plt.savefig(buffer, format='png')
    buffer.seek(0)

    plot_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')

    html_content = f"""
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Budget Bar Graph</title>
            <style>
                body {{
                    display: flex;
                    justify-content: center;
                    align-items: center;
                    height: 100vh; /* Set the height of the body to the full viewport height */
                    margin: 0; /* Remove default margin */
                    background-color: #f0f0f0; /* Set background color */
                }}
                .container {{
                    text-align: center; /* Center the content horizontally */
                }}
                img {{
                    max-width: 100%; /* Ensure the image does not exceed the container width */
                    max-height: 100%; /* Ensure the image does not exceed the container height */
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1>Budget Bar Graph</h1>
                <img src="data:image/png;base64,{plot_base64}" alt="Budget Bar Graph">
            </div>
        </body>
        </html>
    """

    file_path = os.path.join(TEMPLATES_DIR, 'budget_bar_graph.html')

    with open(file_path, 'w') as f:
        f.write(html_content)

    return html_content

def retrieve_finance_data():
    finance_ref = db.collection('finance')
    finance_data = [doc.to_dict() for doc in finance_ref.stream()]
    return finance_data

def screen_ideas(ideas):
    criteria_weights = {
        'budget': 0.3,
        'NPV': 0.4,
        'IRR': 0.3
    }

    finance_data = retrieve_finance_data()
    if not finance_data:
        print("No finance data found in Firestore.")
        return [], []

    screened_ideas = []

    for data in finance_data:
        Budget = data.get('Budget')
        NPV = data.get('NPV')
        IRR = data.get('IRR')
        Name = data.get('Name')  # Ensure 'Name' is properly extracted

        if Budget is None or NPV is None or IRR is None or Name is None:  # Check if 'Name' exists
            print("Missing data in finance document.")
            continue

        total_score = (Budget * criteria_weights['budget'] +
                       NPV * criteria_weights['NPV'] +
                       IRR * criteria_weights['IRR'])

        screened_ideas.append((total_score, Budget, NPV, IRR, Name))  # Include all necessary data

    # Sort scores in descending order
    sorted_screened_ideas = sorted(screened_ideas, key=lambda x: x[0], reverse=True)

    return sorted_screened_ideas

def push_to_firebase(screened_ideas):
    for index, (score, budget, npv, irr, name) in enumerate(screened_ideas, start=1):
        doc_ref = db.collection(u'rank').document(f'idea_{index}')
        doc_ref.set({
            u'score': score,
            u'budget': budget,
            u'npv': npv,
            u'irr': irr,
            u'name': name
        })
    print("Screened ideas pushed to Firebase successfully.")

def generate_html_table(screened_ideas, top_ranks=3):
    html_content = """
    <html>
    <head>
        <title>Screened Ideas</title>
        <style>
            table {
                border-collapse: collapse;
                width: 100%;
                text-align: center;
            }
            th, td {
                border: 1px solid #dddddd;
                text-align: left;
                padding: 8px;
                text-align: center;
            }
            th {
                background-color: #f2f2f2;
                text-align: center;
            }
            @import url('https://fonts.googleapis.com/css2?family=Sen&display=swap');

            html, body {
              height: 100%;
              width:100%;
              margin: 0;
              padding: 0;
              font-size: 10vw;
              background-color: #ddf0e9;
              text-align: center;
            }


            h1, h2 {
              text-align: center;
              margin: 0; 
              font-family: 'Sen', sans-serif;
            }

            #confetti{
              position: absolute;
              left: 0;
              top: 0;
              height: 100%;
              width: 100%;
            }
        </style>
    </head>
    <body>
        <p>Top 3 Screened Ideas</p>
        <table>
            <tr>
                <th>Rank</th>
                <th>Score</th>
                <th>Budget</th>
                <th>NPV</th>
                <th>IRR</th>
                <th>Name</th>
            </tr>
    """

    for rank, (score, budget, npv, irr, name) in enumerate(screened_ideas[:top_ranks], start=1):
        html_content += f"""
            <tr>
                <td>{rank}</td>
                <td>{score}</td>
                <td>{budget}</td>
                <td>{npv}</td>
                <td>{irr}</td>
                <td>{name}</td>
            </tr>
        """

    html_content += """
        </table>
        <!-- Confetti animation -->
        <canvas id="confetti"></canvas>
        <script>
        var retina = window.devicePixelRatio,

            // Math shorthands
            PI = Math.PI,
            sqrt = Math.sqrt,
            round = Math.round,
            random = Math.random,
            cos = Math.cos,
            sin = Math.sin,

            // Local WindowAnimationTiming interface
            rAF = window.requestAnimationFrame,
            cAF = window.cancelAnimationFrame || window.cancelRequestAnimationFrame,
            _now = Date.now || function () {return new Date().getTime();};

        // Local WindowAnimationTiming interface polyfill
        (function (w) {
          /**
                * Fallback implementation.
                */
          var prev = _now();
          function fallback(fn) {
            var curr = _now();
            var ms = Math.max(0, 16 - (curr - prev));
            var req = setTimeout(fn, ms);
            prev = curr;
            return req;
          }

          /**
                * Cancel.
                */
          var cancel = w.cancelAnimationFrame
          || w.webkitCancelAnimationFrame
          || w.clearTimeout;

          rAF = w.requestAnimationFrame
          || w.webkitRequestAnimationFrame
          || fallback;

          cAF = function(id){
            cancel.call(w, id);
          };
        }(window));

        document.addEventListener("DOMContentLoaded", function() {
          var speed = 50,
              duration = (1.0 / speed),
              confettiRibbonCount = 11,
              ribbonPaperCount = 30,
              ribbonPaperDist = 8.0,
              ribbonPaperThick = 8.0,
              confettiPaperCount = 95,
              DEG_TO_RAD = PI / 180,
              RAD_TO_DEG = 180 / PI,
              colors = [
                ["#df0049", "#660671"],
                ["#00e857", "#005291"],
                ["#2bebbc", "#05798a"],
                ["#ffd200", "#b06c00"]
              ];

          function Vector2(_x, _y) {
            this.x = _x, this.y = _y;
            this.Length = function() {
              return sqrt(this.SqrLength());
            }
            this.SqrLength = function() {
              return this.x * this.x + this.y * this.y;
            }
            this.Add = function(_vec) {
              this.x += _vec.x;
              this.y += _vec.y;
            }
            this.Sub = function(_vec) {
              this.x -= _vec.x;
              this.y -= _vec.y;
            }
            this.Div = function(_f) {
              this.x /= _f;
              this.y /= _f;
            }
            this.Mul = function(_f) {
              this.x *= _f;
              this.y *= _f;
            }
            this.Normalize = function() {
              var sqrLen = this.SqrLength();
              if (sqrLen != 0) {
                var factor = 1.0 / sqrt(sqrLen);
                this.x *= factor;
                this.y *= factor;
              }
            }
            this.Normalized = function() {
              var sqrLen = this.SqrLength();
              if (sqrLen != 0) {
                var factor = 1.0 / sqrt(sqrLen);
                return new Vector2(this.x * factor, this.y * factor);
              }
              return new Vector2(0, 0);
            }
          }
          Vector2.Lerp = function(_vec0, _vec1, _t) {
            return new Vector2((_vec1.x - _vec0.x) * _t + _vec0.x, (_vec1.y - _vec0.y) * _t + _vec0.y);
          }
          Vector2.Distance = function(_vec0, _vec1) {
            return sqrt(Vector2.SqrDistance(_vec0, _vec1));
          }
          Vector2.SqrDistance = function(_vec0, _vec1) {
            var x = _vec0.x - _vec1.x;
            var y = _vec0.y - _vec1.y;
            return (x * x + y * y + z * z);
          }
          Vector2.Scale = function(_vec0, _vec1) {
            return new Vector2(_vec0.x * _vec1.x, _vec0.y * _vec1.y);
          }
          Vector2.Min = function(_vec0, _vec1) {
            return new Vector2(Math.min(_vec0.x, _vec1.x), Math.min(_vec0.y, _vec1.y));
          }
          Vector2.Max = function(_vec0, _vec1) {
            return new Vector2(Math.max(_vec0.x, _vec1.x), Math.max(_vec0.y, _vec1.y));
          }
          Vector2.ClampMagnitude = function(_vec0, _len) {
            var vecNorm = _vec0.Normalized;
            return new Vector2(vecNorm.x * _len, vecNorm.y * _len);
          }
          Vector2.Sub = function(_vec0, _vec1) {
            return new Vector2(_vec0.x - _vec1.x, _vec0.y - _vec1.y, _vec0.z - _vec1.z);
          }

          function EulerMass(_x, _y, _mass, _drag) {
            this.position = new Vector2(_x, _y);
            this.mass = _mass;
            this.drag = _drag;
            this.force = new Vector2(0, 0);
            this.velocity = new Vector2(0, 0);
            this.AddForce = function(_f) {
              this.force.Add(_f);
            }
            this.Integrate = function(_dt) {
              var acc = this.CurrentForce(this.position);
              acc.Div(this.mass);
              var posDelta = new Vector2(this.velocity.x, this.velocity.y);
              posDelta.Mul(_dt);
              this.position.Add(posDelta);
              acc.Mul(_dt);
              this.velocity.Add(acc);
              this.force = new Vector2(0, 0);
            }
            this.CurrentForce = function(_pos, _vel) {
              var totalForce = new Vector2(this.force.x, this.force.y);
              var speed = this.velocity.Length();
              var dragVel = new Vector2(this.velocity.x, this.velocity.y);
              dragVel.Mul(this.drag * this.mass * speed);
              totalForce.Sub(dragVel);
              return totalForce;
            }
          }

          function ConfettiPaper(_x, _y) {
            this.pos = new Vector2(_x, _y);
            this.rotationSpeed = (random() * 600 + 800);
            this.angle = DEG_TO_RAD * random() * 360;
            this.rotation = DEG_TO_RAD * random() * 360;
            this.cosA = 1.0;
            this.size = 5.0;
            this.oscillationSpeed = (random() * 1.5 + 0.5);
            this.xSpeed = 40.0;
            this.ySpeed = (random() * 60 + 50.0);
            this.corners = new Array();
            this.time = random();
            var ci = round(random() * (colors.length - 1));
            this.frontColor = colors[ci][0];
            this.backColor = colors[ci][1];
            for (var i = 0; i < 4; i++) {
              var dx = cos(this.angle + DEG_TO_RAD * (i * 90 + 45));
              var dy = sin(this.angle + DEG_TO_RAD * (i * 90 + 45));
              this.corners[i] = new Vector2(dx, dy);
            }
            this.Update = function(_dt) {
              this.time += _dt;
              this.rotation += this.rotationSpeed * _dt;
              this.cosA = cos(DEG_TO_RAD * this.rotation);
              this.pos.x += cos(this.time * this.oscillationSpeed) * this.xSpeed * _dt
              this.pos.y += this.ySpeed * _dt;
              if (this.pos.y > ConfettiPaper.bounds.y) {
                this.pos.x = random() * ConfettiPaper.bounds.x;
                this.pos.y = 0;
              }
            }
            this.Draw = function(_g) {
              if (this.cosA > 0) {
                _g.fillStyle = this.frontColor;
              } else {
                _g.fillStyle = this.backColor;
              }
              _g.beginPath();
              _g.moveTo((this.pos.x + this.corners[0].x * this.size) * retina, (this.pos.y + this.corners[0].y * this.size * this.cosA) * retina);
              for (var i = 1; i < 4; i++) {
                _g.lineTo((this.pos.x + this.corners[i].x * this.size) * retina, (this.pos.y + this.corners[i].y * this.size * this.cosA) * retina);
              }
              _g.closePath();
              _g.fill();
            }
          }
          ConfettiPaper.bounds = new Vector2(0, 0);

          function ConfettiRibbon(_x, _y, _count, _dist, _thickness, _angle, _mass, _drag) {
            this.particleDist = _dist;
            this.particleCount = _count;
            this.particleMass = _mass;
            this.particleDrag = _drag;
            this.particles = new Array();
            var ci = round(random() * (colors.length - 1));
            this.frontColor = colors[ci][0];
            this.backColor = colors[ci][1];
            this.xOff = (cos(DEG_TO_RAD * _angle) * _thickness);
            this.yOff = (sin(DEG_TO_RAD * _angle) * _thickness);
            this.position = new Vector2(_x, _y);
            this.prevPosition = new Vector2(_x, _y);
            this.velocityInherit = (random() * 2 + 4);
            this.time = random() * 100;
            this.oscillationSpeed = (random() * 2 + 2);
            this.oscillationDistance = (random() * 40 + 40);
            this.ySpeed = (random() * 40 + 80);
            for (var i = 0; i < this.particleCount; i++) {
              this.particles[i] = new EulerMass(_x, _y - i * this.particleDist, this.particleMass, this.particleDrag);
            }
            this.Update = function(_dt) {
              var i = 0;
              this.time += _dt * this.oscillationSpeed;
              this.position.y += this.ySpeed * _dt;
              this.position.x += cos(this.time) * this.oscillationDistance * _dt;
              this.particles[0].position = this.position;
              var dX = this.prevPosition.x - this.position.x;
              var dY = this.prevPosition.y - this.position.y;
              var delta = sqrt(dX * dX + dY * dY);
              this.prevPosition = new Vector2(this.position.x, this.position.y);
              for (i = 1; i < this.particleCount; i++) {
                var dirP = Vector2.Sub(this.particles[i - 1].position, this.particles[i].position);
                dirP.Normalize();
                dirP.Mul((delta / _dt) * this.velocityInherit);
                this.particles[i].AddForce(dirP);
              }
              for (i = 1; i < this.particleCount; i++) {
                this.particles[i].Integrate(_dt);
              }
              for (i = 1; i < this.particleCount; i++) {
                var rp2 = new Vector2(this.particles[i].position.x, this.particles[i].position.y);
                rp2.Sub(this.particles[i - 1].position);
                rp2.Normalize();
                rp2.Mul(this.particleDist);
                rp2.Add(this.particles[i - 1].position);
                this.particles[i].position = rp2;
              }
              if (this.position.y > ConfettiRibbon.bounds.y + this.particleDist * this.particleCount) {
                this.Reset();
              }
            }
            this.Reset = function() {
              this.position.y = -random() * ConfettiRibbon.bounds.y;
              this.position.x = random() * ConfettiRibbon.bounds.x;
              this.prevPosition = new Vector2(this.position.x, this.position.y);
              this.velocityInherit = random() * 2 + 4;
              this.time = random() * 100;
              this.oscillationSpeed = random() * 2.0 + 1.5;
              this.oscillationDistance = (random() * 40 + 40);
              this.ySpeed = random() * 40 + 80;
              var ci = round(random() * (colors.length - 1));
              this.frontColor = colors[ci][0];
              this.backColor = colors[ci][1];
              this.particles = new Array();
              for (var i = 0; i < this.particleCount; i++) {
                this.particles[i] = new EulerMass(this.position.x, this.position.y - i * this.particleDist, this.particleMass, this.particleDrag);
              }
            };
            this.Draw = function(_g) {
              for (var i = 0; i < this.particleCount - 1; i++) {
                var p0 = new Vector2(this.particles[i].position.x + this.xOff, this.particles[i].position.y + this.yOff);
                var p1 = new Vector2(this.particles[i + 1].position.x + this.xOff, this.particles[i + 1].position.y + this.yOff);
                if (this.Side(this.particles[i].position.x, this.particles[i].position.y, this.particles[i + 1].position.x, this.particles[i + 1].position.y, p1.x, p1.y) < 0) {
                  _g.fillStyle = this.frontColor;
                  _g.strokeStyle = this.frontColor;
                } else {
                  _g.fillStyle = this.backColor;
                  _g.strokeStyle = this.backColor;
                }
                if (i == 0) {
                  _g.beginPath();
                  _g.moveTo(this.particles[i].position.x * retina, this.particles[i].position.y * retina);
                  _g.lineTo(this.particles[i + 1].position.x * retina, this.particles[i + 1].position.y * retina);
                  _g.lineTo(((this.particles[i + 1].position.x + p1.x) * 0.5) * retina, ((this.particles[i + 1].position.y + p1.y) * 0.5) * retina);
                  _g.closePath();
                  _g.stroke();
                  _g.fill();
                  _g.beginPath();
                  _g.moveTo(p1.x * retina, p1.y * retina);
                  _g.lineTo(p0.x * retina, p0.y * retina);
                  _g.lineTo(((this.particles[i + 1].position.x + p1.x) * 0.5) * retina, ((this.particles[i + 1].position.y + p1.y) * 0.5) * retina);
                  _g.closePath();
                  _g.stroke();
                  _g.fill();
                } else if (i == this.particleCount - 2) {
                  _g.beginPath();
                  _g.moveTo(this.particles[i].position.x * retina, this.particles[i].position.y * retina);
                  _g.lineTo(this.particles[i + 1].position.x * retina, this.particles[i + 1].position.y * retina);
                  _g.lineTo(((this.particles[i].position.x + p0.x) * 0.5) * retina, ((this.particles[i].position.y + p0.y) * 0.5) * retina);
                  _g.closePath();
                  _g.stroke();
                  _g.fill();
                  _g.beginPath();
                  _g.moveTo(p1.x * retina, p1.y * retina);
                  _g.lineTo(p0.x * retina, p0.y * retina);
                  _g.lineTo(((this.particles[i].position.x + p0.x) * 0.5) * retina, ((this.particles[i].position.y + p0.y) * 0.5) * retina);
                  _g.closePath();
                  _g.stroke();
                  _g.fill();
                } else {
                  _g.beginPath();
                  _g.moveTo(this.particles[i].position.x * retina, this.particles[i].position.y * retina);
                  _g.lineTo(this.particles[i + 1].position.x * retina, this.particles[i + 1].position.y * retina);
                  _g.lineTo(p1.x * retina, p1.y * retina);
                  _g.lineTo(p0.x * retina, p0.y * retina);
                  _g.closePath();
                  _g.stroke();
                  _g.fill();
                }
              }
            }
            this.Side = function(x1, y1, x2, y2, x3, y3) {
              return ((x1 - x2) * (y3 - y2) - (y1 - y2) * (x3 - x2));
            }
          }
          ConfettiRibbon.bounds = new Vector2(0, 0);
          confetti = {};
          confetti.Context = function(id) {
            var i = 0;
            var canvas = document.getElementById(id);
            var canvasParent = canvas.parentNode;
            var canvasWidth = canvasParent.offsetWidth;
            var canvasHeight = canvasParent.offsetHeight;
            canvas.width = canvasWidth * retina;
            canvas.height = canvasHeight * retina;
            var context = canvas.getContext('2d');
            var interval = null;
            var confettiRibbons = new Array();
            ConfettiRibbon.bounds = new Vector2(canvasWidth, canvasHeight);
            for (i = 0; i < confettiRibbonCount; i++) {
              confettiRibbons[i] = new ConfettiRibbon(random() * canvasWidth, -random() * canvasHeight * 2, ribbonPaperCount, ribbonPaperDist, ribbonPaperThick, 45, 1, 0.05);
            }
            var confettiPapers = new Array();
            ConfettiPaper.bounds = new Vector2(canvasWidth, canvasHeight);
            for (i = 0; i < confettiPaperCount; i++) {
              confettiPapers[i] = new ConfettiPaper(random() * canvasWidth, random() * canvasHeight);
            }
            this.resize = function() {
              canvasWidth = canvasParent.offsetWidth;
              canvasHeight = canvasParent.offsetHeight;
              canvas.width = canvasWidth * retina;
              canvas.height = canvasHeight * retina;
              ConfettiPaper.bounds = new Vector2(canvasWidth, canvasHeight);
              ConfettiRibbon.bounds = new Vector2(canvasWidth, canvasHeight);
            }
            this.start = function() {
              this.stop()
              var context = this;
              this.update();
            }
            this.stop = function() {
              cAF(this.interval);
            }
            this.update = function() {
              var i = 0;
              context.clearRect(0, 0, canvas.width, canvas.height);
              for (i = 0; i < confettiPaperCount; i++) {
                confettiPapers[i].Update(duration);
                confettiPapers[i].Draw(context);
              }
              for (i = 0; i < confettiRibbonCount; i++) {
                confettiRibbons[i].Update(duration);
                confettiRibbons[i].Draw(context);
              }
              this.interval = rAF(function() {
                confetti.update();
              });
            }
          };
          var confetti = new confetti.Context('confetti');
          confetti.start();
          window.addEventListener('resize', function(event){
            confetti.resize();
          });
        });
        </script>
    </body>
    </html>
    """
    file_path = os.path.join(TEMPLATES_DIR, 'screened_ideas.html')

    with open(file_path, 'w') as f:
        f.write(html_content)
    return html_content

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/extract')
def extract():
    return render_template('extract.html')

@app.route('/extract_info', methods=['POST'])
def handle_extract_info():
    pdf_file = request.files['pdfFile']
    pdf_file.save('sample.pdf')
    info = extract_info('sample.pdf')
    return jsonify(info)

@app.route('/fakedata')
def fakedata():
    finance_data = retrieve_from_firebase()
    html_content = create_html_table(finance_data)
    publish_html(html_content)
    print("HTML page published successfully!")

    return render_template('finance_data.html')

@app.route('/budgetbar')
def budgetbar():
    finance_data = retrieve_from_firebase()
    generate_budget_bar_graph(finance_data)
    return render_template('budget_bar_graph.html')

@app.route('/rank')
def rank():
  screened_ideas = screen_ideas(None)  
  html_table = generate_html_table(screened_ideas, top_ranks=3)
  return render_template('screened_ideas.html')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=80)