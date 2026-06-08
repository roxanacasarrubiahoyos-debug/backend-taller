"""
train.py
========
Script completo para entrenar el clasificador de incidentes vehiculares.
Usa Transfer Learning con MobileNetV2.

Uso:
    python train.py

Requisitos:
    - dataset/ con subcarpetas train/, val/, test/
    - Cada subcarpeta tiene carpetas por clase con las fotos
"""

import os
import json
import numpy as np
import tensorflow as tf
from tensorflow import keras
from tensorflow.keras import layers
from tensorflow.keras.applications import MobileNetV2
from tensorflow.keras.preprocessing.image import ImageDataGenerator
import matplotlib.pyplot as plt
from pathlib import Path

# ─────────────────────────────────────────────
# CONFIGURACIÓN
# ─────────────────────────────────────────────

DATASET_DIR    = Path("dataset")
MODELS_DIR     = Path("models")
MODEL_NAME     = "incident_classifier"

IMG_SIZE       = (224, 224)   # MobileNetV2 espera 224x224
BATCH_SIZE     = 32
EPOCHS_FROZEN  = 10           # Fase 1: solo capas nuevas
EPOCHS_FINETUNE = 20          # Fase 2: también las últimas capas de MobileNetV2
LEARNING_RATE  = 0.001
FINETUNE_LR    = 0.00001      # LR muy bajo para fine-tuning

MODELS_DIR.mkdir(exist_ok=True)


# ─────────────────────────────────────────────
# 1. PREPARAR LOS DATOS
# ─────────────────────────────────────────────

def create_data_generators():
    """
    Crea los generadores de datos con data augmentation para entrenamiento.
    Validación y test sin augmentation (solo normalización).
    """

    # Augmentation solo para entrenamiento
    train_datagen = ImageDataGenerator(
        # Normalización requerida por MobileNetV2
        preprocessing_function=tf.keras.applications.mobilenet_v2.preprocess_input,

        # Data augmentation
        rotation_range=20,           # Rotar hasta 20 grados
        width_shift_range=0.15,      # Desplazar horizontalmente 15%
        height_shift_range=0.15,     # Desplazar verticalmente 15%
        shear_range=0.1,             # Deformación
        zoom_range=0.2,              # Zoom in/out 20%
        horizontal_flip=True,        # Espejo horizontal
        brightness_range=[0.7, 1.3], # Variar brillo (simula distintas luces)
        fill_mode='nearest',         # Rellenar píxeles vacíos
    )

    # Validación y test: SOLO normalización, sin augmentation
    val_test_datagen = ImageDataGenerator(
        preprocessing_function=tf.keras.applications.mobilenet_v2.preprocess_input,
    )

    # Cargar datasets desde carpetas
    train_generator = train_datagen.flow_from_directory(
        DATASET_DIR / "train",
        target_size=IMG_SIZE,
        batch_size=BATCH_SIZE,
        class_mode='categorical',   # One-hot encoding para multiclase
        shuffle=True,
        seed=42,
    )

    val_generator = val_test_datagen.flow_from_directory(
        DATASET_DIR / "val",
        target_size=IMG_SIZE,
        batch_size=BATCH_SIZE,
        class_mode='categorical',
        shuffle=False,
    )

    test_generator = val_test_datagen.flow_from_directory(
        DATASET_DIR / "test",
        target_size=IMG_SIZE,
        batch_size=BATCH_SIZE,
        class_mode='categorical',
        shuffle=False,
    )

    return train_generator, val_generator, test_generator


# ─────────────────────────────────────────────
# 2. CONSTRUIR EL MODELO
# ─────────────────────────────────────────────

def build_model(num_classes: int) -> keras.Model:
    """
    Construye el modelo con Transfer Learning sobre MobileNetV2.

    Arquitectura:
        MobileNetV2 (congelado) → GlobalAvgPool → Dense → Dropout → Softmax

    Args:
        num_classes: Número de clases (carpetas en dataset/train/)

    Returns:
        Modelo Keras compilado
    """

    # ── BASE: MobileNetV2 pre-entrenado con ImageNet
    base_model = MobileNetV2(
        input_shape=(*IMG_SIZE, 3),
        include_top=False,      # Sin la capa final de ImageNet (1000 clases)
        weights='imagenet',     # Descarga pesos pre-entrenados (~14 MB)
    )

    # FASE 1: Congelar TODA la base — solo entrenamos las capas nuevas
    base_model.trainable = False

    print(f"\n📊 MobileNetV2 cargado: {len(base_model.layers)} capas")
    print(f"   Parámetros totales: {base_model.count_params():,}")
    print(f"   Parámetros entrenables (fase 1): 0 (base congelada)")

    # ── CABEZA CUSTOM (capas que SÍ entrenamos)
    inputs = keras.Input(shape=(*IMG_SIZE, 3))

    # Pasar por la base congelada
    x = base_model(inputs, training=False)

    # Reducir dimensiones espaciales a un vector
    x = layers.GlobalAveragePooling2D()(x)

    # Capa densa para aprender patrones de nuestras clases
    x = layers.Dense(256, activation='relu')(x)
    x = layers.BatchNormalization()(x)
    x = layers.Dropout(0.4)(x)              # Regularización

    x = layers.Dense(128, activation='relu')(x)
    x = layers.Dropout(0.3)(x)

    # Capa de salida: una probabilidad por clase
    outputs = layers.Dense(num_classes, activation='softmax')(x)

    model = keras.Model(inputs, outputs)

    # Compilar para la Fase 1
    model.compile(
        optimizer=keras.optimizers.Adam(learning_rate=LEARNING_RATE),
        loss='categorical_crossentropy',
        metrics=['accuracy'],
    )

    trainable_params = sum(
        tf.size(v).numpy() for v in model.trainable_variables
    )
    print(f"   Parámetros entrenables (fase 1): {trainable_params:,}")

    return model, base_model


def unfreeze_for_finetuning(model: keras.Model, base_model: keras.Model):
    """
    FASE 2: Descongela las últimas 30 capas de MobileNetV2 para
    fine-tuning. Esto permite que la base también se ajuste a
    las características específicas de imágenes de vehículos.

    IMPORTANTE: Usar learning rate MUY bajo para no destruir los
    pesos pre-entrenados.
    """
    # Descongelar las últimas 30 capas de la base
    base_model.trainable = True
    total_layers = len(base_model.layers)
    freeze_until = total_layers - 30

    for layer in base_model.layers[:freeze_until]:
        layer.trainable = False

    print(f"\n🔓 Fine-tuning: {30} capas descongeladas de {total_layers}")

    # Recompilar con LR muy bajo
    model.compile(
        optimizer=keras.optimizers.Adam(learning_rate=FINETUNE_LR),
        loss='categorical_crossentropy',
        metrics=['accuracy'],
    )

    trainable_params = sum(
        tf.size(v).numpy() for v in model.trainable_variables
    )
    print(f"   Parámetros entrenables (fase 2): {trainable_params:,}")


# ─────────────────────────────────────────────
# 3. CALLBACKS DE ENTRENAMIENTO
# ─────────────────────────────────────────────

def get_callbacks(phase: str) -> list:
    """
    Callbacks que controlan el entrenamiento automáticamente:
    - ModelCheckpoint: guarda el mejor modelo
    - EarlyStopping: para si deja de mejorar
    - ReduceLROnPlateau: baja el LR si se estanca
    """
    return [
        # Guardar solo el mejor modelo según val_accuracy
        keras.callbacks.ModelCheckpoint(
            filepath=str(MODELS_DIR / f"{MODEL_NAME}_{phase}_best.h5"),
            monitor='val_accuracy',
            save_best_only=True,
            mode='max',
            verbose=1,
        ),

        # Parar si val_accuracy no mejora en X épocas
        keras.callbacks.EarlyStopping(
            monitor='val_accuracy',
            patience=7,              # Épocas de paciencia
            restore_best_weights=True,
            verbose=1,
        ),

        # Reducir LR si val_loss se estanca
        keras.callbacks.ReduceLROnPlateau(
            monitor='val_loss',
            factor=0.5,             # Reduce LR a la mitad
            patience=4,
            min_lr=1e-7,
            verbose=1,
        ),

        # Log para TensorBoard (opcional)
        keras.callbacks.TensorBoard(
            log_dir=str(MODELS_DIR / f"logs_{phase}"),
            histogram_freq=1,
        ),
    ]


# ─────────────────────────────────────────────
# 4. VISUALIZAR RESULTADOS
# ─────────────────────────────────────────────

def plot_history(history_phase1, history_phase2=None):
    """Grafica accuracy y loss del entrenamiento."""
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))

    # Combinar historiales si hay fine-tuning
    if history_phase2:
        acc = history_phase1.history['accuracy'] + history_phase2.history['accuracy']
        val_acc = history_phase1.history['val_accuracy'] + history_phase2.history['val_accuracy']
        loss = history_phase1.history['loss'] + history_phase2.history['loss']
        val_loss = history_phase1.history['val_loss'] + history_phase2.history['val_loss']
        split = len(history_phase1.history['accuracy'])
    else:
        acc = history_phase1.history['accuracy']
        val_acc = history_phase1.history['val_accuracy']
        loss = history_phase1.history['loss']
        val_loss = history_phase1.history['val_loss']
        split = None

    # Accuracy
    axes[0].plot(acc, label='Train Accuracy')
    axes[0].plot(val_acc, label='Val Accuracy')
    if split:
        axes[0].axvline(split, color='r', linestyle='--', label='Fine-tuning inicio')
    axes[0].set_title('Accuracy')
    axes[0].set_xlabel('Época')
    axes[0].legend()
    axes[0].grid(True)

    # Loss
    axes[1].plot(loss, label='Train Loss')
    axes[1].plot(val_loss, label='Val Loss')
    if split:
        axes[1].axvline(split, color='r', linestyle='--', label='Fine-tuning inicio')
    axes[1].set_title('Loss')
    axes[1].set_xlabel('Época')
    axes[1].legend()
    axes[1].grid(True)

    plt.tight_layout()
    plt.savefig(str(MODELS_DIR / 'training_history.png'), dpi=150)
    plt.show()
    print(f"\n📈 Gráfica guardada en {MODELS_DIR}/training_history.png")


# ─────────────────────────────────────────────
# 5. GUARDAR EL MODELO Y LABELS
# ─────────────────────────────────────────────

def save_model_and_labels(model: keras.Model, class_indices: dict):
    """
    Guarda el modelo final y el mapa de clases en JSON.
    El JSON es FUNDAMENTAL — mapea índice numérico → nombre de clase.
    """
    # Guardar modelo en formato .h5 (compatible con la app Django)
    model_path = MODELS_DIR / f"{MODEL_NAME}.h5"
    model.save(str(model_path))
    print(f"\n✅ Modelo guardado: {model_path}")

    # Invertir dict: {nombre: índice} → {índice: nombre}
    # class_indices = {'accident': 0, 'battery': 1, 'engine': 2, ...}
    labels = {str(v): k for k, v in class_indices.items()}
    # labels = {'0': 'accident', '1': 'battery', '2': 'engine', ...}

    labels_path = MODELS_DIR / "labels.json"
    with open(labels_path, 'w', encoding='utf-8') as f:
        json.dump(labels, f, ensure_ascii=False, indent=2)

    print(f"✅ Labels guardado: {labels_path}")
    print(f"   Clases detectadas: {labels}")

    return model_path, labels_path


# ─────────────────────────────────────────────
# 6. FUNCIÓN PRINCIPAL
# ─────────────────────────────────────────────

def main():
    print("=" * 60)
    print("  ENTRENAMIENTO: Clasificador de Incidentes Vehiculares")
    print("=" * 60)

    # Verificar GPU
    gpus = tf.config.list_physical_devices('GPU')
    if gpus:
        print(f"\n🚀 GPU detectada: {gpus[0].name}")
        # Permitir crecimiento de memoria gradual
        tf.config.experimental.set_memory_growth(gpus[0], True)
    else:
        print("\n⚠️  Sin GPU — usando CPU (más lento pero funciona)")

    # ── Paso 1: Datos
    print("\n📁 Cargando dataset...")
    train_gen, val_gen, test_gen = create_data_generators()

    num_classes = len(train_gen.class_indices)
    print(f"\n   Clases encontradas ({num_classes}): {list(train_gen.class_indices.keys())}")
    print(f"   Imágenes de entrenamiento: {train_gen.samples}")
    print(f"   Imágenes de validación:    {val_gen.samples}")
    print(f"   Imágenes de test:          {test_gen.samples}")

    if train_gen.samples < 50:
        print("\n⚠️  ADVERTENCIA: Muy pocas imágenes. Resultado puede ser impreciso.")
        print("   Recomendado: 200+ por clase para resultados confiables.")

    # ── Paso 2: Construir modelo
    print("\n🔨 Construyendo modelo...")
    model, base_model = build_model(num_classes)
    model.summary()

    # ── Paso 3: FASE 1 — Entrenar solo la cabeza
    print("\n" + "=" * 60)
    print("  FASE 1: Entrenando capas nuevas (base congelada)")
    print("=" * 60)

    history1 = model.fit(
        train_gen,
        epochs=EPOCHS_FROZEN,
        validation_data=val_gen,
        callbacks=get_callbacks("fase1"),
        verbose=1,
    )

    val_acc_phase1 = max(history1.history['val_accuracy'])
    print(f"\n✅ Fase 1 completada. Mejor val_accuracy: {val_acc_phase1:.4f} ({val_acc_phase1*100:.1f}%)")

    # ── Paso 4: FASE 2 — Fine-tuning
    print("\n" + "=" * 60)
    print("  FASE 2: Fine-tuning (últimas capas de MobileNetV2)")
    print("=" * 60)

    unfreeze_for_finetuning(model, base_model)

    history2 = model.fit(
        train_gen,
        epochs=EPOCHS_FINETUNE,
        validation_data=val_gen,
        callbacks=get_callbacks("fase2"),
        verbose=1,
    )

    val_acc_phase2 = max(history2.history['val_accuracy'])
    print(f"\n✅ Fase 2 completada. Mejor val_accuracy: {val_acc_phase2:.4f} ({val_acc_phase2*100:.1f}%)")

    # ── Paso 5: Guardar
    save_model_and_labels(model, train_gen.class_indices)

    # ── Paso 6: Gráficas
    plot_history(history1, history2)

    print("\n" + "=" * 60)
    print("  ENTRENAMIENTO COMPLETADO")
    print(f"  Accuracy final en validación: {val_acc_phase2*100:.1f}%")
    print(f"  Modelos guardados en: {MODELS_DIR}/")
    print("=" * 60)


if __name__ == "__main__":
    main()