import shutil
import subprocess
import tempfile
from pathlib import Path


class DocumentConversionError(Exception):
    pass


def convert_word_document(uploaded_file):
    converter = shutil.which('soffice') or shutil.which('libreoffice')
    if not converter:
        raise DocumentConversionError(
            "Word document conversion is unavailable. Please contact an administrator."
        )

    with tempfile.TemporaryDirectory(prefix='curriculum-') as temp_directory:
        temp_path = Path(temp_directory)
        input_path = temp_path / Path(uploaded_file.name).name
        uploaded_file.seek(0)
        with input_path.open('wb') as destination:
            for chunk in uploaded_file.chunks():
                destination.write(chunk)

        profile_path = temp_path / 'libreoffice-profile'
        profile_uri = profile_path.as_uri()
        base_command = [
            converter,
            '--headless',
            f'-env:UserInstallation={profile_uri}',
        ]

        try:
            subprocess.run(
                base_command + ['--convert-to', 'pdf', '--outdir', str(temp_path), str(input_path)],
                check=True,
                capture_output=True,
                text=True,
                timeout=60,
            )
            subprocess.run(
                base_command + ['--convert-to', 'txt:Text', '--outdir', str(temp_path), str(input_path)],
                check=True,
                capture_output=True,
                text=True,
                timeout=60,
            )
        except subprocess.TimeoutExpired as error:
            raise DocumentConversionError(
                "The Word document took too long to convert. Try a smaller document."
            ) from error
        except subprocess.CalledProcessError as error:
            raise DocumentConversionError(
                "The Word document could not be converted. Check that it opens correctly, then try again."
            ) from error
        except OSError as error:
            raise DocumentConversionError(
                "The document conversion service could not process this file. Please contact an administrator."
            ) from error

        pdf_path = temp_path / f'{input_path.stem}.pdf'
        text_path = temp_path / f'{input_path.stem}.txt'
        if not pdf_path.is_file() or not text_path.is_file():
            raise DocumentConversionError(
                "The Word document could not be converted. Check that it opens correctly, then try again."
            )

        extracted_text = text_path.read_text(encoding='utf-8', errors='replace').strip()
        if not extracted_text:
            raise DocumentConversionError(
                "No lesson text could be read from this document. Please check the file or enter the lesson text manually."
            )

        return pdf_path.read_bytes(), extracted_text
