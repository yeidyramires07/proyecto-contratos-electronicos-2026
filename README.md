# Alertas de contratos electrónicos 

Proyecto integrador de cuarto semestre. Une tres materias:
Computación Paralela y Distribuida, Redes e Infraestructura y Analítica y Visualización de Datos.

## Qué hace

- Toma más de 300.00 contratos públicos.

## Carpetas

- `app.py`: la aplicación web (Streamlit).
- `enviar_telegram.py`: envía un mensaje por Telegram. Lo usa la aplicación.
- `procesamiento/`: limpieza de los datos.
  - `reglas.py`: las reglas del proyecto (son contratos públicos electrónicos a nivel regional área Andina).
  - `filtrar_paralelo.py`: limpieza en serie y con multiprocessing, con medición de speedup y eficiencia.
  - `spark_resumen.py`: lo mismo con Apache Spark.
  - `crear_alertas.py`: calcula el saldo pendiente y el nivel de alerta.
- `analisis/`: `eda.py` crea los gráficos exploratorios (carpeta `graficos/`).
- `base_de_datos/`: scripts que crean y cargan la base MySQL y los usuarios.
- `bd/`: esquema de la base de datos y tablas en CSV.
- `utilidades/`: `obtener_chat_id.py` para saber el chat_id de Telegram de una persona.

## Cómo ejecutarlo

```
pip install -r requirements.txt
streamlit run app.py
```



## Privacidad

Se mantiene una sección para solo administradores encargados de dirigirel control de la app

## Integrantes

Camila González 
Camila Pineda
Cristian Guya
Hanna González 
Nardelly Ramírez 
Mariana Rodríguez 

