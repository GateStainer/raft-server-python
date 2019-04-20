import grpc

import chaosmonkey_pb2
import chaosmonkey_pb2_grpc

class CMServer(chaosmonkey_pb2_grpc.ChaosMonkeyServicer):
    def __init__(self, num_server = 3):
        self.fail_mat = [ [ 0.0 for i in range(num_server) ] for i in range(num_server)]
    
    def UploadMatrix(self, request, context):
        try:
            print("CM: Updating new matrix")
            new_mat = []
            for row in range(len(request.rows)):
                r = [ float(v) for v in request.rows[row].vals ]
                new_mat.append(r)
            self.fail_mat = new_mat.copy()
            print("CM: New failure matrix:")
            print(self)
            resp = chaosmonkey_pb2.Status(ret = 0)
            return resp
        except Exception as e:
            print(e)
    
    def UpdateValue(self, request, context):
        try:
            print("CM: Updating new matrix value")
            r = request.row
            c = request.col
            v = request.val
            self.fail_mat[r][c] = v
            print("CM: New failure matrix:")
            print(self)
            resp = chaosmonkey_pb2.Status(ret = 0)
            return resp
        except Exception as e:
            print(e)
    
    def __str__(self):
        return '\n'.join([' '.join([f'{e:.2f}' for e in m]) for m in self.fail_mat])