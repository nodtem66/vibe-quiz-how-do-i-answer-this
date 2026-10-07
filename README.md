# VibeQuiz - How do I answer this?

After tedious lab duty work, I came across an Instagram reel from Voodies Interviews. The interviewer, London, stops people on the street, asks about their major, and then gives them five questions related to their field of study. I tried role-playing the same experience with an LLM, and it quickly became addictive. It was engaging, educational, and genuinely enjoyable.

Then I thought: why not play it together with my friends or students?

That thought became this project: a small, interactive quiz server inspired by Kahoot and Mentimeter, but with a more personal and spontaneous feeling. The quiz is generated in real time, everyone joins from their own device, and the host controls the pace of the game.

The goals are simple:

1. Generate a quiz in real time using an LLM.
2. Start a temporary local server for one quiz session.
3. Let students join from their phones through a shared URL or QR code.
4. Give the host control over each stage of the quiz while everyone plays together.

## Installation

### Requirements

- Python 3.14 or newer
- An OpenRouter API key
- A network connection for quiz generation

### Install dependencies

Create and activate a virtual environment, then install the project dependencies:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
```

If you are not using the project package configuration, install the required packages directly:

```powershell
python -m pip install fastapi granian openrouter pydantic
```

### Configure OpenRouter

Set the API key and model as environment variables:

```powershell
$env:OPENROUTER_API_KEY = "your-openrouter-api-key"
$env:OPENROUTER_MODEL = "your-openrouter-model"
```

Alternatively, create a `.env` file in the project root:

```text
OPENROUTER_API_KEY=your-openrouter-api-key
OPENROUTER_MODEL=your-openrouter-model
```

Do not commit `.env` or expose your API key. The included launcher loads these values before starting the server.

## Quick user guide

### 1. Start the server

From the project directory, run:

```powershell
python run.py --topic "Biomedical engineering" --questions 5
```

The terminal prints a private host URL containing a long access token, for example:

```text
[INFO] Host URL: http://localhost:8000/?token=<generated-token>
```

Open this URL on the host device. The token protects the host controls from accidental access by students.

### 2. Share the player URL

Students use the public player URL:

```text
http://<host-ip>:8000/
```

Replace `<host-ip>` with the host computer's local network address. The host and students must be connected to the same network. You can turn this URL into a QR code for quick access.

### 3. Run the quiz

1. Open the tokenized URL in the host's browser.
2. Ask students to open the player URL or scan its QR code.
3. Students choose a name, or use the dice button to generate one.
4. Duplicate names are rejected so each player can be identified reliably.
5. Click **Start Game** on the host frontend.
6. Students select an answer on each question.
7. Click **Reveal Answer**, then **Next Question** to continue.
8. At the end, the host and players can view the leaderboard.

The player browser stores its player ID locally, so refreshing the page can rejoin the current session with the same name.