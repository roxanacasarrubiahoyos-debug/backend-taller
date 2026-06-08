"""
predict_test.py
===============
Prueba el modelo con cualquier foto.
Muestra todas las probabilidades por clase.

Uso: python predict_test.py ruta/a/tu/foto.jpg
"""

import sys
import json
import numpy as np
import tensorflow as tf
from PIL import Image
from pathlib import Path

MODELS_DIR = Path("models")
IMG_SIZE   = (224, 224)


def predict_single(image_path: str):
    # Cargar modelo y labels
    model = tf.keras.models.load_model(str(MODELS_DIR / "incident_classifier.h5"))

    with open(MODELS_DIR / "labels.json") as f:
        labels = json.load(f)

    # Preprocesar imagen
    img = Image.open(image_path).convert('RGB').resize(IMG_SIZE)
    arr = np.array(img, dtype=np.float32)
    arr = tf.keras.applications.mobilenet_v2.preprocess_input(arr)
    arr = np.expand_dims(arr, axis=0)   # (1, 224, 224, 3)

    # Predecir
    predictions = model.predict(arr, verbose=0)[0]

    # Ordenar por confianza
    results = [
        {'class': labels[str(i)], 'confidence': float(predictions[i])}
        for i in range(len(predictions))
    ]
    results.sort(key=lambda x: x['confidence'], reverse=True)

    print(f"\n🔍 Análisis de: {image_path}")
    print("─" * 40)
    for r in results:
        bar = "█" * int(r['confidence'] * 20)
        print(f"  {r['class']:<15} {bar:<20} {r['confidence']:.1%}")

    winner = results[0]
    print(f"\n✅ Resultado: {winner['class'].upper()} ({winner['confidence']:.1%} confianza)")

    if winner['confidence'] < 0.5:
        print("⚠️  Confianza baja — el sistema marcará como 'uncertain'")

    return winner


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python predict_test.py ruta/foto.jpg")
        sys.exit(1)
    predict_single(sys.argv[1])