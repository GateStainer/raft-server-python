# Generated by the gRPC Python protocol compiler plugin. DO NOT EDIT!
import grpc

from src import chaosmonkey_pb2 as src_dot_chaosmonkey__pb2


class ChaosMonkeyStub(object):
  # missing associated documentation comment in .proto file
  pass

  def __init__(self, channel):
    """Constructor.

    Args:
      channel: A grpc.Channel.
    """
    self.UploadMatrix = channel.unary_unary(
        '/chaosmonkey.ChaosMonkey/UploadMatrix',
        request_serializer=src_dot_chaosmonkey__pb2.ConnMatrix.SerializeToString,
        response_deserializer=src_dot_chaosmonkey__pb2.Status.FromString,
        )
    self.UpdateValue = channel.unary_unary(
        '/chaosmonkey.ChaosMonkey/UpdateValue',
        request_serializer=src_dot_chaosmonkey__pb2.MatValue.SerializeToString,
        response_deserializer=src_dot_chaosmonkey__pb2.Status.FromString,
        )


class ChaosMonkeyServicer(object):
  # missing associated documentation comment in .proto file
  pass

  def UploadMatrix(self, request, context):
    # missing associated documentation comment in .proto file
    pass
    context.set_code(grpc.StatusCode.UNIMPLEMENTED)
    context.set_details('Method not implemented!')
    raise NotImplementedError('Method not implemented!')

  def UpdateValue(self, request, context):
    # missing associated documentation comment in .proto file
    pass
    context.set_code(grpc.StatusCode.UNIMPLEMENTED)
    context.set_details('Method not implemented!')
    raise NotImplementedError('Method not implemented!')


def add_ChaosMonkeyServicer_to_server(servicer, server):
  rpc_method_handlers = {
      'UploadMatrix': grpc.unary_unary_rpc_method_handler(
          servicer.UploadMatrix,
          request_deserializer=src_dot_chaosmonkey__pb2.ConnMatrix.FromString,
          response_serializer=src_dot_chaosmonkey__pb2.Status.SerializeToString,
      ),
      'UpdateValue': grpc.unary_unary_rpc_method_handler(
          servicer.UpdateValue,
          request_deserializer=src_dot_chaosmonkey__pb2.MatValue.FromString,
          response_serializer=src_dot_chaosmonkey__pb2.Status.SerializeToString,
      ),
  }
  generic_handler = grpc.method_handlers_generic_handler(
      'chaosmonkey.ChaosMonkey', rpc_method_handlers)
  server.add_generic_rpc_handlers((generic_handler,))