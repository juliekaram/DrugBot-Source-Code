# DrugBot

source code for DrugBot, an application that I worked on while working as a research trainee at the Ma'ayan Lab at the Icahn School of Medicine during summer 2020.

application available for download: https://maayanlab.slack.com/apps/A016AFALY4B-drugbot

full repository: https://github.com/MaayanLab/Drugs-and-Genes-SlackBot.

## Development

The entrypoint of the application is in `DrugBot/app/app.py`; do not change the name of the file or directory.

### Getting Started
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Running in development
```bash
source venv/bin/activate
python run.py
```

And visit <http://localhost:8080/DrugBot>.

### Installing new dependencies

#### Python dependencies
Ensure you update `requirements.txt` whenever installing a new dependency with `pip`.

#### System dependencies
In the case of extra (debian) system dependencies, add them to `deps.txt`.

## Deployment

### Build for deployment
```bash
docker-compose build app
```

### Deploy
```bash
docker-compose push app
```

### Execute locally
```
docker-compose run app
```
