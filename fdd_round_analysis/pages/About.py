import streamlit as st
import pandas as pd
from pandas.io.json import json_normalize
import json
import numpy as np

siteHeader = st.container()

with siteHeader:
  st.title('About')
  st.markdown('Platform to showcase future in round analysis.')
  st.markdown('This current mock up has details on the previous Alpha round but could be tailored to fit Beta Round inquires as well.')
