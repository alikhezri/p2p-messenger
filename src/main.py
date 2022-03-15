# import random
import socket
import sys
import os
from time import sleep
from peer import TCP_PORT, UDP_PORT, Peer

SERVER = socket.gethostbyname(socket.gethostname())
DISCOVER_SLEEP_TIME = 2


if __name__ == '__main__':
    mypeer = Peer(host=SERVER, tcp_port=TCP_PORT, udp_port=UDP_PORT)
    if not mypeer.start():
        sys.exit(os.EX_IOERR)
    ACTIVE = True
    while ACTIVE:
        try:
            command = input("command > ")
            words = command.split()
            if words:
                if words[0] == r"\quit" or words[0] == r"\q":
                    print("Good Bye!")
                    ACTIVE = False
                    mypeer.end_gracefully()
                elif words[0] == r"\connect" or words[0] == r"\c":
                    try:
                        if len(words[1:]) == 2:
                            host = words[1]
                            port = int(words[2])
                        elif len(words[1:]) == 1:
                            addr = words[1].split(':')
                            host = addr[0]
                            port = int(addr[1])
                        else:
                            # TODO: show correct usage
                            continue
                        mypeer.connect((host, port))
                    except Exception as ex:
                        print(f"Couldn't connect: {ex}")
                elif words[0] == r"\d" or words[0] == r"\disconnect":
                    try:
                        if len(words[1:]) == 1:
                            uuid = words[1]
                            mypeer.disconnect(uuid=uuid)
                        else:
                            print(f"Command '{words[0]}' gets 1 arguement")
                            continue
                    except Exception as ex:
                        print(f"Couldn't perform disconnection: {ex}")
                elif words[0] == r"\me":
                    print(f"My Info: {mypeer.host}:{mypeer.port}")
                    pass
                elif words[0] == r"\ls":
                    active_neighbors = mypeer.list_actives()
                    if active_neighbors:
                        print("Active Available Neighbors:")
                        number = 0
                        for uuid, addr in active_neighbors:
                            number += 1
                            print(f"\t{number}) {uuid} at {addr}")
                    else:
                        print("No active neighbors available!")
                    inactive_neighbors = mypeer.list_inactives()
                    if inactive_neighbors:
                        print("Inactive Available Neighbors:")
                        number = 0
                        for uuid, addr in inactive_neighbors:
                            number += 1
                            print(f"\t{number}) {uuid} at {addr}")
                    else:
                        print("No inactive neighbors available!")
                elif words[0] == r"\message" or words[0] == r"\chat":
                    try:
                        if len(words[1:]) == 1:
                            uuid = words[1]
                            mypeer.chat(uuid=uuid)
                        else:
                            # TODO: show correct usage
                            continue
                    except Exception as ex:
                        print(f"Couldn't start chat: {ex}")
                elif words[0] == r"\discover":
                    mypeer.discover()
                    sleep(DISCOVER_SLEEP_TIME)
                    discovereds = mypeer.get_discovered()
                    if discovereds:
                        print("Discovered Peers:")
                        number = 0
                        for d in discovereds:
                            number += 1
                            print(f"\t{number}) {d}")
                    else:
                        print("No Neighbor Discoverd")
                elif words[0] == r"\help" or words[0] == r"\h":
                    # TODO: help should be added
                    pass
                else:
                    continue
        except KeyboardInterrupt:
            print()
            pass
            # ACTIVE = False
            # mypeer.end_forcefully()
