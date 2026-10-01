"""Punto de entrada compatible para iniciar STOCKFLOW."""

from backend.app import app


if __name__ == '__main__':
    app.run(debug=False, threaded=True, host='0.0.0.0', port=5000)
