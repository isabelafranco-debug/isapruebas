import argparse
from pathlib import Path
import httpx

def main():
    from jupiter.climate import LIMIT, POWER_URL, power_parameters, inspect, check_power
    from jupiter.db import PILOT
    parser = argparse.ArgumentParser()
    parser.add_argument("--lon",type=float,default=PILOT[0])
    parser.add_argument("--lat",type=float,default=PILOT[1])
    parser.add_argument("--output",type=Path,required=True)
    args = parser.parse_args()
    with httpx.stream("GET",POWER_URL,params=power_parameters(args.lon,args.lat),timeout=45) as r:
        r.raise_for_status()
        with args.output.open("xb") as file:
            total = 0
            try:
                for part in r.iter_bytes():
                    total += len(part)
                    if total > LIMIT:
                        raise RuntimeError("La descarga supera 20 MiB.")
                    file.write(part)
            except BaseException:
                file.close()
                args.output.unlink(missing_ok=True)
                raise
    header,_=inspect(args.output,"climate")
    check_power(header,args.lon,args.lat)
    print(args.output)

if __name__=="__main__":
    main()
