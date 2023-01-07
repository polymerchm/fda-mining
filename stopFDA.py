import redis

stop_state_key = "STOPSTATE"

def main():
    r = redis.Redis()
    r.set(stop_state_key,'stop')
    print("Request fdaMain to stop at before next webrequest")
    
if __name__ == '__main__':
    main()

