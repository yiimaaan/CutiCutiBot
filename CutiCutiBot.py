from flask import Flask, request, jsonify, render_template
from flask_sqlalchemy import SQLAlchemy
import os
from openai import OpenAI
from dotenv import load_dotenv

# --- SETUP OPENAI ---
load_dotenv()
load_dotenv("app.env")

api_key = os.getenv("OPENAI_API_KEY")

if not api_key:
    print("❌ ERROR: API KEY TIDAK DITEMUI! Sila check file .env anda.")
else:
    print(f"✅ OpenAI API Key ditemui. Menggunakan model: gpt-5-nano")

client = OpenAI(api_key=api_key)

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///gamification.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)


# --- USER MODEL ---
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    points = db.Column(db.Integer, default=0)
    level = db.Column(db.Integer, default=1)
    stickers = db.Column(db.Text, default="")


with app.app_context():
    db.create_all()

conversation_history = []
SYSTEM_PERSONA = "You are 'CutiCutiBot', a Malaysian travel expert. Promote tourism in Northern, Central, Southern, East Coast, and East Malaysia. Keep responses helpful, enthusiastic, and short."


@app.route("/")
def home():
    return render_template("index_CutiCutiBot.html")


def calculate_level(points):
    return (points // 100) + 1


# --- CHAT FUNCTION ---
def generate_response(user_input, username):
    global conversation_history

    conversation_history.append({"role": "user", "content": user_input})
    if len(conversation_history) > 10:
        conversation_history = conversation_history[-10:]

    messages = [{"role": "system", "content": SYSTEM_PERSONA}] + conversation_history

    try:

        response = client.chat.completions.create(
            model="gpt-5-nano",
            messages=messages

        )
        bot_response = response.choices[0].message.content.strip()

    except Exception as e:
        print(f"OpenAI Error: {e}")
        bot_response = "⚠️ Maaf, ada masalah sambungan dengan OpenAI. Sila cuba lagi."

    conversation_history.append({"role": "assistant", "content": bot_response})

    user = User.query.filter_by(username=username).first()
    if user:
        user.points += 5
        user.level = calculate_level(user.points)
        db.session.commit()

    return bot_response


@app.route("/chat", methods=["POST"])
def chat():
    data = request.json
    user_input = data.get("message", "")
    username = data.get("username", "guest")

    user = User.query.filter_by(username=username).first()
    if not user:
        user = User(username=username)
        db.session.add(user)
        db.session.commit()

    response_text = generate_response(user_input, username)
    user = User.query.filter_by(username=username).first()

    return jsonify({
        "response": response_text,
        "points": user.points,
        "level": user.level,
        "stickers": user.stickers
    })


# --- QUIZ FUNCTION ---
@app.route("/generate_quiz", methods=["POST"])
def generate_quiz():
    data = request.json
    topic = data.get("topic", "Malaysian tourism")

    prompt = (
        f"Create a multiple-choice travel trivia question about {topic} in Malaysia. "
        "Strictly follow this format:\n"
        "Question Text\n"
        "A) Option 1\n"
        "B) Option 2\n"
        "C) Option 3\n"
        "D) Option 4\n"
        "Correct Answer: Option Text\n"
        "Do not add any other text."
    )

    try:
        response = client.chat.completions.create(
            model="gpt-5-nano",
            messages=[
                {"role": "system", "content": "You are a quiz generator."},
                {"role": "user", "content": prompt}
            ]
        )

        quiz_content = response.choices[0].message.content.strip()
        lines = [line for line in quiz_content.split("\n") if line.strip()]

        if len(lines) < 5:
            raise ValueError("Format Error")

        question = lines[0]
        choices = []
        correct_answer = ""

        for line in lines[1:]:
            line = line.strip()
            if "Correct Answer:" in line:
                correct_answer = line.split(":")[-1].strip()
            elif line.startswith(("A)", "B)", "C)", "D)")):
                choices.append(line)

        return jsonify({"question": question, "choices": choices[:4], "correct_answer": correct_answer})

    except Exception as e:
        print(f"Quiz Error: {e}")
        return jsonify({
            "question": "⚠️ Error. Fallback: Ibu negara Malaysia?",
            "choices": ["A) KL", "B) Penang", "C) Johor", "D) Sabah"],
            "correct_answer": "KL"
        })


@app.route("/quiz_answer", methods=["POST"])
def quiz_answer():
    data = request.json
    user_answer = data.get("answer", "").strip()
    correct_answer = data.get("correct_answer", "").strip()
    username = data.get("username", "guest")

    def clean_text(text):
        if len(text) >= 3 and text[1] == ')' and text[0].upper() in "ABCD":
            return text.split(" ", 1)[-1].strip()
        return text

    user_answer_clean = clean_text(user_answer)
    correct_answer_clean = clean_text(correct_answer)

    user = User.query.filter_by(username=username).first()
    if not user:
        user = User(username=username)
        db.session.add(user)
        db.session.commit()

    if user_answer_clean.lower() == correct_answer_clean.lower():
        user.points += 20
        user.level = calculate_level(user.points)
        db.session.commit()
        return jsonify({
            "correct": True,
            "message": "Betul! +20 Mata! Get ready for BONUS GAME!",
            "points": user.points,
            "level": user.level,
            "stickers": user.stickers
        })
    else:
        return jsonify({
            "correct": False,
            "message": "Salah la pulak.",
            "points": user.points,
            "level": user.level,
            "stickers": user.stickers
        })


@app.route("/game_reward", methods=["POST"])
def game_reward():
    data = request.json
    username = data.get("username", "guest")
    points_won = data.get("points", 0)

    user = User.query.filter_by(username=username).first()
    if user:
        user.points += points_won
        user.level = calculate_level(user.points)
        stickers = user.stickers.split(',') if user.stickers else []
        stickers.append("✈️")
        user.stickers = ','.join([s for s in stickers if s])
        db.session.commit()
        return jsonify({
            "message": f"Game Over! Menang {points_won} mata!",
            "points": user.points,
            "level": user.level,
            "stickers": user.stickers
        })
    return jsonify({"message": "Error saving points"})


if __name__ == "__main__":
    app.run(debug=True)