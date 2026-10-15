from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "career.db"
CONFIG_PATH = ROOT / "config" / "career.json"
JOB_DIR = ROOT / "job-search"
INTERVIEW_DIR = ROOT / "interview-coach"
VACANCIES_DIR = JOB_DIR / "vacancies"
TRACKER_PATH = JOB_DIR / "tracker.xlsx"
