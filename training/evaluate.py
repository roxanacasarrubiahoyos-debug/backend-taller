"""
evaluate.py
===========
Evalúa el modelo entrenado con el conjunto de TEST.
Muestra: accuracy, matriz de confusión, reporte por clase.

Uso: python evaluate.py
"""

import json
import numpy as np
import tensorflow as tf
from tensorflow.keras.preprocessing.image import ImageDataGenerator
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.metrics import classification_report, confusion_matrix
from pathlib import Path

MODELS_DIR  = Path("models")
DATASET_DIR = Path("dataset")
IMG_SIZE    = (224, 224)
BATCH_SIZE  = 32


def evaluate():
    # ── Cargar modelo y labels
    model = tf.keras.models.load_model(str(MODELS_DIR / "incident_classifier.h5"))

    with open(MODELS_DIR / "labels.json") as f:
        labels = json.load(f)

    class_names = [labels[str(i)] for i in range(len(labels))]
    print(f"Clases: {class_names}")

    # ── Cargar test set
    test_datagen = ImageDataGenerator(
        preprocessing_function=tf.keras.applications.mobilenet_v2.preprocess_input,
    )
    test_gen = test_datagen.flow_from_directory(
        DATASET_DIR / "test",
        target_size=IMG_SIZE,
        batch_size=BATCH_SIZE,
        class_mode='categorical',
        shuffle=False,
    )

    # ── Evaluación global
    print("\n📊 Evaluando en test set...")
    loss, accuracy = model.evaluate(test_gen, verbose=1)
    print(f"\n✅ Test Accuracy: {accuracy*100:.2f}%")
    print(f"   Test Loss:     {loss:.4f}")

    # ── Predicciones para métricas detalladas
    y_pred_probs = model.predict(test_gen, verbose=1)
    y_pred = np.argmax(y_pred_probs, axis=1)
    y_true = test_gen.classes

    # ── Reporte por clase
    print("\n📋 Reporte por clase:")
    print(classification_report(y_true, y_pred, target_names=class_names))

    # ── Matriz de confusión (visual)
    cm = confusion_matrix(y_true, y_pred)

    plt.figure(figsize=(10, 8))
    sns.heatmap(
        cm,
        annot=True,
        fmt='d',
        cmap='Blues',
        xticklabels=class_names,
        yticklabels=class_names,
    )
    plt.title('Matriz de Confusión — Clasificador de Incidentes')
    plt.ylabel('Real')
    plt.xlabel('Predicho')
    plt.tight_layout()
    plt.savefig(str(MODELS_DIR / "confusion_matrix.png"), dpi=150)
    plt.show()

    print(f"\n📈 Matriz de confusión guardada en {MODELS_DIR}/confusion_matrix.png")

    # ── Análisis de errores: ver qué confunde el modelo
    print("\n❌ Errores más comunes:")
    errors = []
    for i, (true, pred) in enumerate(zip(y_true, y_pred)):
        if true != pred:
            errors.append({
                'file': test_gen.filenames[i],
                'true': class_names[true],
                'pred': class_names[pred],
                'confidence': float(y_pred_probs[i][pred]),
            })

    errors.sort(key=lambda x: x['confidence'], reverse=True)
    for err in errors[:10]:  # Top 10 errores más confiados (los peores)
        print(f"  {err['file']}")
        print(f"    Real: {err['true']} | Predicho: {err['pred']} ({err['confidence']:.1%})")


if __name__ == "__main__":
    evaluate()