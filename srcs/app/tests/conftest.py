import os

os.environ["AUTH_SECRET_KEY"] = "unit-test-secret-key-0123456789abcdef0123"
os.environ["AUTH_DUMMY_HASH"] = (
    "$2b$12$4.Ddy7ZCvMZyKnbIBhiAR.gvSwa7lCMTKtqO2rb8Gh/J6ce2sFbVa"
)
os.environ["FRONTEND_ORIGINS"] = "http://localhost:5173"
os.environ["LOG_LEVEL"] = "WARNING"
