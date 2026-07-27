#!/usr/bin/env python3
"""
Script d'automatisation pour la creation de dossiers de location immobiliere.
Applique un filigrane de securite sur tous les PDF d'un dossier 'original'
et les sauvegarde dans un dossier nomme d'apres le destinataire.
"""

import re
import sys
from pathlib import Path
from typing import List, Optional

from pypdf import PdfReader, PdfWriter
from pypdf.generic import DictionaryObject, NameObject, ArrayObject, FloatObject
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.colors import Color
import io
import click


# ---------------------------------------------------------------------------
# Configuration du filigrane
# ---------------------------------------------------------------------------
WATERMARK_TEXT_TEMPLATE = (
    "Document exclusivement reserve a la candidature de location transmise a "
    "{recipient} via {ad_url} - Ne peut etre utilise a d'autres fins."
)

WATERMARK_COLOR = Color(0.5, 0.5, 0.5, alpha=0.3)  # Gris semi-transparent
WATERMARK_FONT = "Helvetica"
WATERMARK_FONT_SIZE = 14
WATERMARK_ANGLE = 45  # degres, diagonale
WATERMARK_SPACING_Y = 200  # espacement vertical entre les lignes en points
WATERMARK_SPACING_X = 150  # espacement horizontal en points pour repetition


def sanitize_directory_name(raw_name: str) -> str:
    """
    Nettoie le nom du destinataire pour creer un nom de dossier valide.
    Remplace les espaces par des underscores et supprime les caracteres speciaux.
    """
    # Remplacer les espaces et apostrophes par underscore
    name = re.sub(r"[\s']+", "_", raw_name)
    # Supprimer tout ce qui n'est pas alphanumerique, underscore ou tiret
    name = re.sub(r"[^\w\-]", "", name)
    # Eviter les noms vides
    if not name:
        name = "Dossier_Destinataire"
    return name


def generate_watermark_overlay(page_width: float, page_height: float,
                               text: str) -> io.BytesIO:
    """
    Genere une page PDF transparente contenant le texte du filigrane repete
    en diagonale. Renvoie un buffer BytesIO pret a etre fusionne.
    """
    packet = io.BytesIO()
    c = canvas.Canvas(packet, pagesize=(page_width, page_height))
    c.setFont(WATERMARK_FONT, WATERMARK_FONT_SIZE)
    c.setFillColor(WATERMARK_COLOR)

    # Calculer la zone de repetition pour couvrir toute la page
    start_x = -page_width * 0.5
    end_x = page_width * 1.5
    start_y = -page_height * 0.5
    end_y = page_height * 1.5

    y = start_y
    while y < end_y:
        x = start_x
        while x < end_x:
            c.saveState()
            # Translation au point de depart puis rotation
            c.translate(x, y)
            c.rotate(WATERMARK_ANGLE)
            c.drawString(0, 0, text)
            c.restoreState()
            x += WATERMARK_SPACING_X
        y += WATERMARK_SPACING_Y

    c.save()
    packet.seek(0)
    return packet


def apply_watermark_to_pdf(pdf_path: Path, watermark_text: str) -> bytes:
    """
    Applique le filigrane sur chaque page d'un PDF.
    Retourne le contenu du PDF filigrane sous forme de bytes.
    """
    reader = PdfReader(pdf_path)
    writer = PdfWriter()

    for page in reader.pages:
        # Recuperer les dimensions reelles de la page
        mediabox = page.mediabox
        page_width = float(mediabox.width)
        page_height = float(mediabox.height)

        # Generer le calque de filigrane adapte a cette page
        overlay_buffer = generate_watermark_overlay(
            page_width, page_height, watermark_text
        )
        overlay_pdf = PdfReader(overlay_buffer)
        overlay_page = overlay_pdf.pages[0]

        # Fusionner le filigrane sur la page originale
        page.merge_page(overlay_page)
        writer.add_page(page)

    output_buffer = io.BytesIO()
    writer.write(output_buffer)
    return output_buffer.getvalue()


def process_all_pdfs(source_dir: Path, output_dir: Path, watermark_text: str) -> List[Path]:
    """
    Parcourt tous les PDF du dossier source, applique le filigrane et les
    sauvegarde dans le dossier de sortie. Retourne la liste des fichiers crees.
    """
    if not source_dir.exists():
        raise click.ClickException(
            f"Le dossier source '{source_dir}' est introuvable. "
            f"Veuillez le creer et y placer vos PDF."
        )

    pdf_files = list(source_dir.glob("*.pdf"))
    if not pdf_files:
        raise click.ClickException(
            f"Aucun fichier PDF trouve dans le dossier '{source_dir}'."
        )

    # Creer le dossier de sortie s'il n'existe pas
    output_dir.mkdir(parents=True, exist_ok=True)
    created_files = []

    for pdf_path in pdf_files:
        try:
            click.echo(f"  Traitement de : {pdf_path.name}")
            watermarked_content = apply_watermark_to_pdf(pdf_path, watermark_text)

            output_path = output_dir / pdf_path.name
            output_path.write_bytes(watermarked_content)
            created_files.append(output_path)
        except Exception as e:
            click.echo(
                f"  [ERREUR] Impossible de traiter '{pdf_path.name}': {e}",
                err=True
            )

    return created_files


@click.command()
@click.option(
    "--annonce-url",
    prompt="URL de l'annonce immobiliere",
    help="Lien de l'annonce pour contextualisation et inclusion dans le filigrane."
)
@click.option(
    "--destinataire",
    prompt="Nom du destinataire (agence, agent ou proprietaire)",
    help="Nom complet du destinataire du dossier."
)
def main(annonce_url: str, destinataire: str):
    """
    Application CLI pour securiser des documents de location avec un filigrane.
    Lit les PDF depuis le dossier './original' et les sauvegarde dans un dossier
    nomme selon le destinataire.
    """
    # Construction du texte du filigrane personnalise
    watermark_text = WATERMARK_TEXT_TEMPLATE.format(
        recipient=destinataire,
        ad_url=annonce_url
    )

    # Chemins des dossiers
    source_dir = Path.cwd() / "original"
    output_dir_name = sanitize_directory_name(destinataire)
    output_dir = Path.cwd() / output_dir_name

    click.echo(f"\nDossier source : {source_dir}")
    click.echo(f"Dossier de sortie : {output_dir}")
    click.echo(f"Texte du filigrane : \"{watermark_text}\"")
    click.echo("\nDebut du traitement...")

    created_files = process_all_pdfs(source_dir, output_dir, watermark_text)

    if created_files:
        click.echo(f"\nTraitement termine avec succes. {len(created_files)} fichier(s) genere(s) :")
        for f in created_files:
            click.echo(f"  - {f}")
    else:
        click.echo("\nAucun fichier n'a pu etre traite. Verifiez les erreurs ci-dessus.", err=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
