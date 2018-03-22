import json
from multiprocessing import Process, Queue, Lock, Manager
import threading, time
import numpy as np
import paho.mqtt.client as mqtt


Global = Manager().Namespace()

CMD_TRAIN_START   = 0
CMD_TRAIN_FINISH  = 1
CMD_TRAIN_STATUS = 2
CMD_DELETE_NAME = 3
CMD_GET_NAMES = 4
CMD_MODULE_UPDATE = 5


class FaceRecognitonProcess(Process):
    def __init__(self, frameq, retq, cmdq, cmdretq):
        Process.__init__(self)
        self.frameq = frameq
        self.retq = retq
        self.cmdq = cmdq
        self.cmdretq = cmdretq
        self.training = 0
        self.broadmqtt = mqtt.Client()
        self.broadmqtt.connect("localhost", 1883, 60)
        self.broadmqtt.subscribe("NXP_CMD_MODULE_UPDATE", qos=1)
        self.broadmqtt.on_message = self.module_update

    def sendResult(self, ret):
        try:
            self.retq.put_nowait(ret)
        except Exception as e:
            return None, None

    def getCmd(self):
        try:
            return self.cmdq.get()
        except Exception as e:
            return None, None

    def reciveFrame(self):
        try:
            return self.frameq.get_nowait()
        except Exception as e:
            return None

    def training_callback(self):
        self.training = 0

    def module_update(self, client, userdata, message):
        print "in module_update"
        self.cmdq.put((CMD_MODULE_UPDATE, None))

    def run(self):
        import face_recg as face_recg
        self.broadmqtt.loop_start()
        
        print("Face recognition engine initialized")
        print("Please open browser and visite https://[board-ip]:5000/")
        while (1):
#            try:
                if self.cmdq.full():
                    cmd, param = self.getCmd()
                    if cmd == CMD_TRAIN_START:
                        print("CMD_TRAIN_START")
                        if self.training == 0:
                            rets = face_recg.train_start(param)
                            self.training = 1
                            self.poscount = {"Left" : 0, "Right": 0, "Center": 0}
                        else:
                            rets = False
                    elif cmd == CMD_TRAIN_FINISH:
                        print("CMD_TRAIN_FINISH")
                        if self.training == 1:
                            rets = face_recg.train_finish(self.training_callback)
                            self.training = 2
                        else:
                            rets = False
                    elif cmd == CMD_TRAIN_STATUS:
                        if self.training == 0:
                            rets = (0, None)
                            self.broadmqtt.publish("NXP_CMD_MODULE_UPDATE", "nouse")
                        elif self.training == 1:
                            rets = (1, self.poscount)
                        else:
                            rets = (2, None)
                    elif cmd == CMD_DELETE_NAME:
                        print("CMD_DELETE_NAME")
                        rets = face_recg.delete_name(param)
                        if rets = True:
                            self.broadmqtt.publish("NXP_CMD_MODULE_UPDATE", "nouse")
                    elif cmd == CMD_MODULE_UPDATE:
                        face_recg.load_modules()
                        continue
                    elif cmd == CMD_GET_NAMES:
                        print("CMD_GET_NAMES")
                        rets = face_recg.get_names()
                    else:
                        continue
                    self.cmdretq.put(rets)
                elif self.frameq.empty() != True:
                    inFrame= self.reciveFrame()
                    if inFrame is None:
                        continue
                    if self.training == 1:
                        rets = face_recg.train_process_people(inFrame)
                        print rets
                        if len(rets[0]) == 1 and rets[0][0]["pos"] == "Center":
                             self.poscount["Center"] += 1
                        elif len(rets[0]) == 1 and rets[0][0]["pos"] == "Left":
                             self.poscount["Left"] += 1
                        elif len(rets[0]) == 1 and rets[0][0]["pos"] == "Right":
                             self.poscount["Right"] += 1
                    elif self.training == 0:
                        rets = face_recg.recog_process_frame(inFrame)
                        if len(rets) == 1 and rets[0]["pos"] == "Center" and rets[0]["name"] != " ":
                            name = rets[0]["name"]
                            if name not in self.history_names:
                                self.history_names[name] = [0, int(time.time() * 1000)]
                            else:
                                self.history_names[name][0] += 1

                            if self.history_names[name][0] == 5:
                                self.sendGuidence(name)
                    else:
                        rets = face_recg.detect_people(inFrame)
                    self.sendResult(rets)
#            except Exception as e:
#                pass

frameq = None
retq = None
cmdq = None
cmdretq = None



def initEngine():
    global frameq,retq, cmdq,cmdretq
    
    frameq = Queue(maxsize = 1)
    retq = Queue(maxsize = 1)
    cmdq = Queue(maxsize = 1)
    cmdretq = Queue(maxsize = 1)

    process = FaceRecognitonProcess(frameq, retq, cmdq, cmdretq)
    process.start()

def proImageFile(imgf):
    frame = np.array(imgf)
    proCvFrame(frame)

def proCvFrame(frame):
    try:
        if (frameq.full()):
            frameq.get_nowait()
        frameq.put(frame)
    except Exception as e:
        print(e)

def trainStart(name):
    cmdq.put((CMD_TRAIN_START, name))
    ret = cmdretq.get()
    return ret

def getTrainStatus():
    cmdq.put((CMD_TRAIN_STATUS, None))
    ret = cmdretq.get()
    return ret

def trainFinish():
    cmdq.put((CMD_TRAIN_FINISH, None))
    ret = cmdretq.get()
    return ret

def getResult():
    try:
        rets= retq.get_nowait()
        return rets
    except Exception as e:
        return None

def deleteName(name):
    cmdq.put((CMD_DELETE_NAME, name))
    ret = cmdretq.get()
    return ret

def getNames():
    cmdq.put((CMD_GET_NAMES, None))
    ret = cmdretq.get()
    return ret

initEngine()
