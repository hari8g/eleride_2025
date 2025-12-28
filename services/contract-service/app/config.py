from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "Contract Generation Service"
    env: str = "dev"
    template_dir: str = "templates"
    generated_dir: str = "generated"
    template_filename: str = "rider_agreement_template.docx"
    
    # PDF conversion (optional)
    enable_pdf: bool = True
    libreoffice_path: str = "/usr/bin/libreoffice"  # Default Linux path
    
    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()

