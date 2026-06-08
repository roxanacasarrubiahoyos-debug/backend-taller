import numpy as np
import json
from django.conf import settings
import os


def _normalize_incident_labels(raw):
    """Lista de códigos IncidentType; si labels.json es otro formato, usar lista por defecto."""
    default = [
        'battery', 'tire', 'accident', 'engine',
        'locksmith', 'overheating', 'other',
    ]
    if isinstance(raw, list) and raw:
        if all(isinstance(x, str) for x in raw):
            return raw
    if isinstance(raw, dict) and raw:
        keys = sorted(raw.keys(), key=lambda k: int(k) if str(k).isdigit() else 0)
        vals = [raw[k] for k in keys]
        if vals and all(v in default for v in vals):
            return vals
        print(
            'WARNING: TF_LABELS no coincide con tipos de incidente. '
            'Usando etiquetas por defecto para clasificación.'
        )
    return default


class IncidentClassifier:
    """
    Clasifica imágenes de vehículos usando TensorFlow.
    Modelo: MobileNetV2 con transfer learning (placeholder).
    Clases: battery, tire, accident, engine, locksmith, overheating, other

    El modelo .h5 se carga UNA VEZ al iniciar (singleton).
    """
    _instance = None
    _model = None
    _labels = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._load_model()
        return cls._instance

    def _load_model(self):
        """Carga el modelo TensorFlow y las etiquetas."""
        try:
            # Verificar si existe el archivo de etiquetas
            if os.path.exists(settings.TF_LABELS_PATH):
                with open(settings.TF_LABELS_PATH) as f:
                    loaded = json.load(f)
                self._labels = _normalize_incident_labels(loaded)
            else:
                self._labels = _normalize_incident_labels([])

            # Intentar cargar el modelo si existe
            if os.path.exists(settings.TF_MODEL_PATH):
                import tensorflow as tf
                self._model = tf.keras.models.load_model(settings.TF_MODEL_PATH)
            else:
                # Modelo no disponible - se usarán predicciones placeholder
                self._model = None
                print("WARNING: TensorFlow model not found. Using placeholder predictions.")

        except Exception as e:
            print(f"Error loading model: {e}")
            self._model = None
            self._labels = _normalize_incident_labels([])

    def predict(self, image_path: str) -> dict:
        """
        Retorna:
        {
            'label': 'tire',
            'confidence': 0.87,
            'all_scores': {'battery': 0.05, 'tire': 0.87, ...},
            'success': True
        }
        """
        try:
            if self._model is None:
                # Placeholder: retornar predicción simulada
                return self._placeholder_prediction()

            import tensorflow as tf
            img = tf.keras.preprocessing.image.load_img(image_path, target_size=(224, 224))
            arr = tf.keras.preprocessing.image.img_to_array(img)
            arr = tf.keras.applications.mobilenet_v2.preprocess_input(arr)
            arr = np.expand_dims(arr, axis=0)

            predictions = self._model.predict(arr)[0]
            scores = {self._labels[i]: float(predictions[i]) for i in range(len(self._labels))}
            best_label = max(scores, key=scores.get)

            return {
                'label': best_label,
                'confidence': scores[best_label],
                'all_scores': scores,
                'success': True,
            }
        except Exception as e:
            return {
                'label': 'uncertain',
                'confidence': 0.0,
                'success': False,
                'error': str(e)
            }

    def _placeholder_prediction(self) -> dict:
        """
        Retorna una predicción placeholder cuando el modelo no está disponible.
        """
        labels = _normalize_incident_labels(self._labels)
        if not labels:
            labels = ['uncertain']
        # Sin modelo entrenado no forzamos una clase específica.
        # Dejamos baja confianza para que el pipeline combine con texto/audio.
        base = round(1.0 / len(labels), 4)
        scores = {label: base for label in labels}
        pick = 'uncertain' if 'uncertain' in labels else labels[0]
        confidence = 0.0 if pick == 'uncertain' else scores[pick]

        return {
            'label': pick,
            'confidence': confidence,
            'all_scores': scores,
            'success': True,
            'source': 'placeholder',
            'note': 'Using placeholder predictions (model not loaded)',
        }
