"""Cloud entrypoint: public market data only, no account or trading features."""
import runpy
import json
from pathlib import Path
import streamlit as st
from cloud_feed import CloudFeed, prepare

@st.cache_resource
def public_feed():
    return CloudFeed(prepare()).start()

# Shared mode initializes historical panels without independent signal generation.
config = json.loads(Path(__file__).with_name("shared_feed.json").read_text())
prepare()
if config.get("mode") != "personal_shared":
    public_feed()
runpy.run_path(str(Path(__file__).with_name("public_viewer.py")), run_name="__main__")
