import os
os.environ["EV_SAAS_MODE"] = "1"
os.environ.pop("OPENAI_API_KEY", None)

from .app import create_saas_app
from .settings import Settings

app = create_saas_app(Settings.from_env())
