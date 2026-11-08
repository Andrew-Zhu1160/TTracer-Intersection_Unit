import random

def generate_ray(test_mode):
        if test_mode == "FIXED":
            #formate: ray origin tuple, ray direction tuple
            return (0,0,0),(0.5,0.5,0.5)

        else:
            #formate: ray origin tuple, ray direction tuple
            return (random.randint(-255,255),random.randint(-255,255),random.randint(-255,255)),
            (random.random(),random.random(),random.random())