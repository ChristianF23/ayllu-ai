import os
import yaml
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger("AylluOKFReader")

class OKFConcept:
    def __init__(self, metadata: Dict[str, Any], content: str, file_path: str):
        self.metadata = metadata
        self.content = content
        self.file_path = file_path
        self.concept_type = metadata.get("type", "Unknown")
        self.title = metadata.get("title", "Untitled")
        self.status = metadata.get("status", "active")

    def __repr__(self):
        return f"<OKFConcept type='{self.concept_type}' title='{self.title}'>"


class OKFBundleReader:
    """
    Lector de Bundles de Conocimiento bajo el estándar OKF v0.2.
    Parsea Frontmatter YAML y extrae esquemas, reglas y consultas canónicas.
    """
    def __init__(self, knowledge_dir: str = "knowledge"):
        self.knowledge_dir = knowledge_dir
        self.concepts: Dict[str, OKFConcept] = {}

    def load_bundle(self) -> int:
        """
        Escanea la carpeta knowledge/ y carga todos los archivos .md parseando su Frontmatter.
        """
        if not os.path.exists(self.knowledge_dir):
            logger.warning(f"Directorio de conocimiento '{self.knowledge_dir}' no encontrado.")
            return 0

        loaded_count = 0
        for root, _, files in os.walk(self.knowledge_dir):
            for file in files:
                if file.endswith(".md"):
                    full_path = os.path.join(root, file)
                    concept = self._parse_file(full_path)
                    if concept:
                        # Clave de identificación relacional (ej: tables/cost_logs.md)
                        rel_path = os.path.relpath(full_path, self.knowledge_dir).replace("\\", "/")
                        self.concepts[rel_path] = concept
                        loaded_count += 1

        logger.info(f"✓ Cargados {loaded_count} conceptos OKF v0.2 desde '{self.knowledge_dir}'")
        return loaded_count

    def _parse_file(self, file_path: str) -> Optional[OKFConcept]:
        """
        Lee un archivo Markdown y separa el Frontmatter YAML del cuerpo del texto.
        """
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                raw_text = f.read()

            if not raw_text.startswith("---"):
                logger.warning(f"El archivo '{file_path}' no contiene Frontmatter YAML delimitado por '---'.")
                return None

            parts = raw_text.split("---", 2)
            if len(parts) < 3:
                logger.warning(f"Estructura YAML inválida en '{file_path}'.")
                return None

            yaml_header = parts[1]
            markdown_body = parts[2].strip()

            metadata = yaml.safe_load(yaml_header) or {}
            return OKFConcept(metadata=metadata, content=markdown_body, file_path=file_path)

        except Exception as e:
            logger.error(f"❌ Error al parsear concepto OKF en '{file_path}': {str(e)}")
            return None

    def get_context_summary(self) -> str:
        """
        Genera un resumen empaquetado del conocimiento para inyectar al System Prompt del Orquestador.
        """
        summary_lines = ["=== BUNDLE DE CONOCIMIENTO SISTÉMICO (OKF v0.2) ==="]
        for rel_path, concept in self.concepts.items():
            if concept.status != "active":
                continue
            summary_lines.append(f"\n--- CONCEPTO: [{concept.concept_type}] {concept.title} ({rel_path}) ---")
            summary_lines.append(f"Descripción: {concept.metadata.get('description', 'Sin descripción')}")
            summary_lines.append(concept.content)

        return "\n".join(summary_lines)


# Instancia global del lector OKF
okf_reader = OKFBundleReader()