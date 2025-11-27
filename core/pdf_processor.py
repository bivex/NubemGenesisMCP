#!/usr/bin/env python3
"""
PDF Processor para NubemSuperFClaude
Procesa y extrae contenido de archivos PDF
"""

import os
import logging
from pathlib import Path
from typing import Optional, Dict, Any
import PyPDF2
import pdfplumber
from PIL import Image
import pytesseract

logger = logging.getLogger(__name__)


class PDFProcessor:
    """Procesador de archivos PDF con OCR opcional"""

    def __init__(self):
        self.supported_formats = ['.pdf']

    def process_pdf(self, pdf_path: str) -> Dict[str, Any]:
        """
        Procesa un archivo PDF y extrae su contenido

        Args:
            pdf_path: Ruta al archivo PDF

        Returns:
            Dict con el contenido extraído
        """
        if not os.path.exists(pdf_path):
            return {
                "error": f"El archivo no existe: {pdf_path}",
                "content": None
            }

        result = {
            "file_path": pdf_path,
            "file_name": os.path.basename(pdf_path),
            "content": "",
            "metadata": {},
            "pages": [],
            "images": [],
            "tables": []
        }

        try:
            # Intentar con pdfplumber primero (mejor para tablas y formato)
            with pdfplumber.open(pdf_path) as pdf:
                result["metadata"] = {
                    "pages": len(pdf.pages),
                    "author": pdf.metadata.get('Author', ''),
                    "title": pdf.metadata.get('Title', ''),
                    "subject": pdf.metadata.get('Subject', ''),
                    "creator": pdf.metadata.get('Creator', '')
                }

                for i, page in enumerate(pdf.pages):
                    # Extraer texto
                    text = page.extract_text()
                    if text:
                        result["content"] += f"\n--- Página {i+1} ---\n{text}"
                        result["pages"].append({
                            "page": i+1,
                            "text": text
                        })

                    # Extraer tablas
                    tables = page.extract_tables()
                    if tables:
                        result["tables"].extend([{
                            "page": i+1,
                            "data": table
                        } for table in tables])

        except Exception as e:
            logger.warning(f"pdfplumber falló, intentando con PyPDF2: {e}")

            # Fallback a PyPDF2
            try:
                with open(pdf_path, 'rb') as file:
                    pdf_reader = PyPDF2.PdfReader(file)

                    result["metadata"]["pages"] = len(pdf_reader.pages)

                    for i, page in enumerate(pdf_reader.pages):
                        text = page.extract_text()
                        if text:
                            result["content"] += f"\n--- Página {i+1} ---\n{text}"
                            result["pages"].append({
                                "page": i+1,
                                "text": text
                            })

            except Exception as e2:
                logger.error(f"Error procesando PDF: {e2}")
                result["error"] = str(e2)

        # Si no hay contenido, intentar OCR
        if not result["content"].strip():
            logger.info("PDF sin texto extraíble, intentando OCR...")
            result["content"] = self._ocr_pdf(pdf_path)
            result["ocr_used"] = True

        return result

    def _ocr_pdf(self, pdf_path: str) -> str:
        """
        Aplica OCR a un PDF que no tiene texto extraíble

        Args:
            pdf_path: Ruta al archivo PDF

        Returns:
            Texto extraído por OCR
        """
        try:
            # Convertir PDF a imágenes y aplicar OCR
            import pdf2image

            pages = pdf2image.convert_from_path(pdf_path)
            text = ""

            for i, page in enumerate(pages):
                # Aplicar OCR a cada página
                page_text = pytesseract.image_to_string(page, lang='spa+eng')
                text += f"\n--- Página {i+1} (OCR) ---\n{page_text}"

            return text

        except Exception as e:
            logger.error(f"Error en OCR: {e}")
            return f"Error aplicando OCR: {e}"

    def extract_summary(self, pdf_content: str, max_chars: int = 1000) -> str:
        """
        Extrae un resumen del contenido del PDF

        Args:
            pdf_content: Contenido del PDF
            max_chars: Máximo de caracteres para el resumen

        Returns:
            Resumen del contenido
        """
        if not pdf_content:
            return "Sin contenido disponible"

        # Tomar las primeras líneas significativas
        lines = pdf_content.split('\n')
        summary = []
        char_count = 0

        for line in lines:
            line = line.strip()
            if line and not line.startswith('---'):
                summary.append(line)
                char_count += len(line)
                if char_count >= max_chars:
                    break

        return '\n'.join(summary[:10])  # Máximo 10 líneas

    def analyze_vconnect_vision(self, pdf_data: Dict) -> Dict[str, Any]:
        """
        Análisis específico para VConnect Vision v4

        Args:
            pdf_data: Datos extraídos del PDF

        Returns:
            Análisis estructurado
        """
        content = pdf_data.get("content", "")

        analysis = {
            "project_name": "VConnect Vision v4",
            "detected_sections": [],
            "key_concepts": [],
            "ai_opportunities": [],
            "technical_requirements": []
        }

        # Buscar secciones clave
        sections_keywords = [
            "introducción", "introduction",
            "objetivos", "objectives", "goals",
            "arquitectura", "architecture",
            "tecnología", "technology",
            "implementación", "implementation",
            "resultados", "results"
        ]

        for keyword in sections_keywords:
            if keyword.lower() in content.lower():
                analysis["detected_sections"].append(keyword)

        # Identificar conceptos clave
        ai_keywords = [
            "artificial intelligence", "machine learning", "deep learning",
            "neural network", "nlp", "computer vision", "automation",
            "predictive", "analytics", "data science"
        ]

        for keyword in ai_keywords:
            if keyword.lower() in content.lower():
                analysis["key_concepts"].append(keyword)

        # Sugerir oportunidades de IA basadas en el contenido
        if "vision" in pdf_data["file_name"].lower():
            analysis["ai_opportunities"].extend([
                "Computer Vision para análisis de imágenes",
                "OCR avanzado para extracción de datos",
                "Reconocimiento de patrones visuales"
            ])

        if "connect" in pdf_data["file_name"].lower():
            analysis["ai_opportunities"].extend([
                "NLP para análisis de comunicaciones",
                "Chatbots inteligentes para soporte",
                "Análisis predictivo de conexiones"
            ])

        # Agregar oportunidades genéricas siempre aplicables
        analysis["ai_opportunities"].extend([
            "Automatización de procesos con RPA + IA",
            "Dashboard inteligente con insights automáticos",
            "Sistema de recomendaciones basado en ML",
            "Análisis de sentimiento y feedback",
            "Predicción de tendencias y anomalías"
        ])

        return analysis


# Función helper para uso directo
def process_pdf_file(pdf_path: str) -> Dict[str, Any]:
    """
    Procesa un archivo PDF y retorna su contenido estructurado

    Args:
        pdf_path: Ruta al archivo PDF

    Returns:
        Diccionario con el contenido y análisis del PDF
    """
    processor = PDFProcessor()

    # Procesar el PDF
    pdf_data = processor.process_pdf(pdf_path)

    # Si es VConnect Vision, hacer análisis específico
    if "vconnect" in pdf_path.lower():
        pdf_data["analysis"] = processor.analyze_vconnect_vision(pdf_data)

    # Agregar resumen
    pdf_data["summary"] = processor.extract_summary(pdf_data.get("content", ""))

    return pdf_data


if __name__ == "__main__":
    # Test
    import sys
    if len(sys.argv) > 1:
        pdf_path = sys.argv[1]
        result = process_pdf_file(pdf_path)

        print(f"📄 Archivo: {result['file_name']}")
        print(f"📊 Páginas: {result['metadata'].get('pages', 'Unknown')}")
        print(f"📝 Resumen:\n{result['summary'][:500]}...")

        if result.get("analysis"):
            print("\n🤖 Oportunidades de IA detectadas:")
            for opp in result["analysis"]["ai_opportunities"][:5]:
                print(f"  • {opp}")