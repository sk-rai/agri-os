#!/usr/bin/env python3
"""Regression for production-safe configuration."""
import os
import sys
from pathlib import Path
from pydantic import ValidationError
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"backend"))
CONFIG=(ROOT/"backend/app/core/config.py").read_text()
AUTH=(ROOT/"backend/app/modules/auth/api.py").read_text()
SERVICE=(ROOT/"backend/app/modules/auth/service.py").read_text()
MAIN=(ROOT/"backend/app/main.py").read_text()
ENV=(ROOT/".env.example").read_text()
CHECKS=[
 (CONFIG,'APP_ENVIRONMENT: Literal["development", "test", "production"]',"Environment modes are bounded"),
 (CONFIG,"reject_development_security_in_production","Production validation exists"),
 (CONFIG,"JWT_SECRET must be a non-default secret","JWT fails closed"),
 (CONFIG,"DB_PASSWORD must not use the development default","DB password fails closed"),
 (CONFIG,"AUTH_EXPOSE_DEV_OTP must be false","OTP exposure fails closed"),
 (CONFIG,"CORS_ALLOWED_ORIGINS must not contain local","CORS fails closed"),
 (SERVICE,"JWT_SECRET = settings.JWT_SECRET","JWT comes from settings"),
 (AUTH,"if settings.AUTH_EXPOSE_DEV_OTP","OTP exposure is gated"),
 (MAIN,"settings.cors_allowed_origins","CORS comes from settings"),
 (MAIN,"if settings.API_DOCS_ENABLED else None","Docs are gated"),
 (ENV,"APP_ENVIRONMENT=production","Production contract is documented"),
]
def main():
    for text,needle,label in CHECKS:
        if needle not in text: raise AssertionError(f"{label}: missing {needle!r}")
        print(f"PASS {label}")
    os.environ.update({"APP_ENVIRONMENT":"production","JWT_SECRET":"x"*48,
      "DB_PASSWORD":"non-development-secret","AUTH_EXPOSE_DEV_OTP":"false",
      "API_DOCS_ENABLED":"false","CORS_ALLOWED_ORIGINS":"https://admin.example.invalid"})
    from app.core.config import Settings
    safe=Settings(_env_file=None)
    assert safe.APP_ENVIRONMENT=="production" and not safe.AUTH_EXPOSE_DEV_OTP
    print("PASS Safe production settings validate")
    os.environ["JWT_SECRET"]="agrios-dev-secret-change-in-production"
    try: Settings(_env_file=None)
    except ValidationError: print("PASS Development JWT rejected in production")
    else: raise AssertionError("Unsafe production JWT was accepted")
    print("PRODUCTION SECURITY SETTINGS STATIC CONTRACT PASSED")
    return 0
if __name__=="__main__": raise SystemExit(main())
