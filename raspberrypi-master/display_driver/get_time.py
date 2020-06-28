from datetime import datetime

def get_time(): 
    time_string = datetime.now().strftime('%Y-%m-%d %H|%M')
    return time_string