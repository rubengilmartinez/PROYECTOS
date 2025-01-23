import json
import urllib
import boto3
import csv
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime, timedelta
import os

# Conexión a S3, DynamoDB y SNS
s3 = boto3.resource('s3')
dynamodb = boto3.resource('dynamodb')
sns = boto3.client('sns')

# Referencias a DynamoDB y SNS
temp_table = dynamodb.Table('TemperaturasMarMenor')
sns_topic_arn = 'arn:aws:sns:us-east-1:471112833695:alerta-desviacion-temperatura'

def round_decimal(value):
    return value.quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP)

def lambda_handler(event, context):
    print("Event received by Lambda function: " + json.dumps(event, indent=2))

    bucket = event['Records'][0]['s3']['bucket']['name']
    key = urllib.parse.unquote_plus(event['Records'][0]['s3']['object']['key'])
    local_filename = f"/tmp/{os.path.basename(key)}"

    try:
        # Descargar el archivo desde S3
        s3.meta.client.download_file(bucket, key, local_filename)

        # Procesar el archivo CSV
        with open(local_filename) as csvfile:
            reader = csv.DictReader(csvfile, delimiter=',')
            data = {}

            for row in reader:
                fecha = datetime.strptime(row['Fecha'], '%Y/%m/%d')
                mes = fecha.strftime('%Y/%m')
                temp_media = round_decimal(Decimal(row['Medias']))
                desviacion = round_decimal(Decimal(row['Desviaciones']))

                if mes not in data:
                    data[mes] = {
                        'max_temp': temp_media,
                        'max_sd': desviacion,
                        'mean_temp_sum': temp_media,
                        'mean_temp_count': 1,
                        'records': [(fecha, temp_media, desviacion)]
                    }
                else:
                    data[mes]['max_temp'] = max(data[mes]['max_temp'], temp_media)
                    data[mes]['max_sd'] = max(data[mes]['max_sd'], desviacion)
                    data[mes]['mean_temp_sum'] += temp_media
                    data[mes]['mean_temp_count'] += 1
                    data[mes]['records'].append((fecha, temp_media, desviacion))

                # Notificar si la desviación supera 0.5
                if desviacion > Decimal('0.5'):
                    send_sns_notification(fecha.strftime('%Y/%m/%d'), desviacion)

            # Procesar y actualizar DynamoDB con datos combinados
            for mes, metrics in data.items():
                try:
                    # Consultar el registro existente en la base de datos
                    existing_item = temp_table.get_item(Key={'Fecha': mes})
                    existing_item = existing_item.get('Item', {})

                    # Calcular max_diff_temp considerando el mes anterior
                    previous_month = (datetime.strptime(mes, '%Y/%m') - timedelta(days=1)).strftime('%Y/%m')

                    # Caso 1: Mes anterior en la base de datos
                    previous_item = temp_table.get_item(Key={'Fecha': previous_month}).get('Item', {})
                    previous_max_temp_db = Decimal(previous_item.get('max_temp', 0))

                    # Caso 2: Mes anterior en el archivo actual
                    if previous_month in data:
                        previous_max_temp_file = data[previous_month]['max_temp']
                    else:
                        previous_max_temp_file = Decimal('0')

                    # Determinar el máximo del mes anterior (base de datos o archivo)
                    previous_max_temp = max(previous_max_temp_db, previous_max_temp_file)

                    combined_max_temp = max(metrics['max_temp'], Decimal(existing_item.get('max_temp', 0)))
                    combined_max_sd = max(metrics['max_sd'], Decimal(existing_item.get('max_sd', 0)))

                    total_mean_temp_sum = metrics['mean_temp_sum'] + Decimal(existing_item.get('mean_temp', 0)) * Decimal(existing_item.get('mean_temp_count', 0))
                    total_mean_temp_count = metrics['mean_temp_count'] + Decimal(existing_item.get('mean_temp_count', 0))
                    combined_mean_temp = round_decimal(total_mean_temp_sum / total_mean_temp_count)

                    max_diff_temp = round_decimal(combined_max_temp - previous_max_temp)

                    # Actualizar o insertar el registro
                    temp_table.put_item(
                        Item={
                            'Fecha': mes,
                            'max_temp': combined_max_temp,
                            'max_sd': combined_max_sd,
                            'mean_temp': combined_mean_temp,
                            'max_diff_temp': max_diff_temp,
                            'mean_temp_count': total_mean_temp_count
                        }
                    )

                except Exception as e:
                    print(e)
                    raise Exception(f"Error updating DynamoDB for {mes}.")

    except Exception as e:
        print(e)
        raise Exception(f"Error processing file {key} from bucket {bucket}.")
    
    finally:
        # Limpiar el archivo temporal
        if os.path.exists(local_filename):
            os.remove(local_filename)

    return "Processing completed."

def send_sns_notification(date, deviation):
    message = (f"Alerta de desviación: La desviación estándar semanal en {date} "
               f"ha superado el umbral (valor: {deviation}).")
    try:
        sns.publish(
            TopicArn=sns_topic_arn,
            Message=message,
            Subject='Alerta de Temperatura')
        print(f"Notification sent for {date}. Deviation: {deviation}")
    except Exception as e:
        print(e)
        raise Exception("Error sending notification.")