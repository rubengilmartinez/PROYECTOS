import boto3
from flask import Flask, jsonify, request

app = Flask(__name__)

dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
table = dynamodb.Table('TemperaturasMarMenor')

def query_data_from_dynamodb(month_year):
    """Consulta DynamoDB por la clave de partición basada en Fecha (YYYY/MM)."""
    try:
        response = table.query(
            KeyConditionExpression=boto3.dynamodb.conditions.Key('Fecha').eq(month_year)
        )
        return response.get('Items', [])
    except Exception as e:
        print(f"Error querying DynamoDB: {e}")
        return []

@app.route('/health')
def health_check():
    """Endpoint para comprobación de salud"""
    return jsonify({'status': 'healthy'}), 200

@app.route('/maxdiff', methods=['GET'])
def max_diff():
    year = request.args.get('year')
    month = request.args.get('month')

    if not (year and month):
        return jsonify({'error': 'Year and month are required parameters'}), 400

    month_year = f"{year}/{month.zfill(2)}"
    data = query_data_from_dynamodb(month_year)

    if data:
        return jsonify({'max_diff_temperatures': data[0].get('max_diff_temp', 'Data not available')})
    else:
        return jsonify({'error': 'Data not found'}), 404

@app.route('/sd', methods=['GET'])
def standard_deviation():
    year = request.args.get('year')
    month = request.args.get('month')

    if not (year and month):
        return jsonify({'error': 'Year and month are required parameters'}), 400

    month_year = f"{year}/{month.zfill(2)}"
    data = query_data_from_dynamodb(month_year)

    if data:
        return jsonify({'max_standard_deviation': data[0].get('max_sd', 'Data not available')})
    else:
        return jsonify({'error': 'Data not found'}), 404

@app.route('/temp', methods=['GET'])
def mean_temp():
    year = request.args.get('year')
    month = request.args.get('month')

    if not (year and month):
        return jsonify({'error': 'Year and month are required parameters'}), 400

    month_year = f"{year}/{month.zfill(2)}"
    data = query_data_from_dynamodb(month_year)

    if data:
        return jsonify({'mean_temperature': data[0].get('mean_temp', 'Data not available')})
    else:
        return jsonify({'error': 'Data not found'}), 404

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)


