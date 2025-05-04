# pico_api.py
import ujson, socket, gc
from machine import Pin
from main import fetch_weather, irrigation_time, Kc_today, rz_mm, total_area, relay
from main     import get_last_logged_date, log_data, get_today_str

_last_log = get_last_logged_date()

def handle_client(cl):
    req   = cl.recv(1024).decode()
    method, path = req.split(' ',2)[:2]

    # — GET /status
    if method=="GET" and path=="/status":
        tmax, rh, energy = fetch_weather()
        et0  = __import__('main').rf_model.score([tmax, rh, energy])
        avail = __import__('main').soil_available_water_depth(20.0, rz_mm)
        t_pump, etc = irrigation_time(Kc_today, et0, avail, total_area)
        status = {
          "tmax": tmax, "rh": rh, "energy": energy,
          "ET0": et0, "Kc": Kc_today, "rz_mm": rz_mm,
          "ETc": etc, "avail": avail,
          "pump_on": bool(relay.value())
        }
        cl.send("HTTP/1.0 200 OK\r\nContent-Type: application/json\r\n\r\n")
        cl.send(ujson.dumps(status))

    # — GET /log
    elif method=="GET" and path=="/log":
        try:
            data = open("daily_log.csv","r").read()
            cl.send("HTTP/1.0 200 OK\r\nContent-Type: text/csv\r\n\r\n")
            cl.send(data)
        except:
            cl.send("HTTP/1.0 500 ERROR\r\n\r\n")

    # — POST /config
    elif method=="POST" and path=="/config":
        body = req.split("\r\n\r\n",1)[1]
        cfg  = ujson.loads(body)
        # apply new config to main.py globals:
        import main
        main.crop       = cfg["crop"]
        main.Y,main.Mo,main.Da = map(int, cfg["plant_date"].split('-'))
        main.ps, main.rs= cfg["ps"], cfg["rs"]
        main.days       = main.get_days_after_planting(main.Y, main.Mo, main.Da)
        main.Kc_today   = main.linear_interpolate(main.days, main.crop_kc_profile[cfg["crop"]])
        main.rz_m       = main.linear_interpolate(main.days, main.crop_root_profile[cfg["crop"]])
        main.rz_mm      = main.rz_m * 1000
        main.area_per_plant = main.ps * main.rs / 10000
        main.total_area     = main.area_per_plant * main.n_plants
        cl.send("HTTP/1.0 200 OK\r\nContent-Type: application/json\r\n\r\n")
        cl.send('{"status":"ok"}')

    else:
        cl.send("HTTP/1.0 404 Not Found\r\n\r\n")

    cl.close()
    gc.collect()

def start(port=80):
    addr = socket.getaddrinfo("0.0.0.0", port)[0][-1]
    s = socket.socket()
    s.bind(addr)
    s.listen(1)
    print("🌐 API listening on", addr)
    import _thread
    _thread.start_new_thread(lambda: [_ for _ in iter(lambda: s.accept() and handle_client(s.accept()[0]), None)], ())
