from rest_framework.views import exception_handler
from rest_framework.response import Response


def custom_exception_handler(exc, context):
    response = exception_handler(exc, context)
    if response is not None:
        if isinstance(response.data, dict) and 'detail' in response.data:
            response.data = {'message': response.data['detail']}
        elif isinstance(response.data, list):
            response.data = {'message': response.data[0] if response.data else '请求错误'}
        return response

    return Response({'message': str(exc)}, status=500)
