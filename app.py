"""Cloud entrypoint: public market data only, no account or trading features."""
import runpy
from pathlib import Path
import streamlit as st
from cloud_feed import CloudFeed,prepare

@st.cache_resource
def public_feed():
    return CloudFeed(prepare()).start()

public_feed()
runpy.run_path(str(Path(__file__).with_name('public_viewer.py')),run_name='__main__')
