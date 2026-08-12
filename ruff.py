import os
from pathlib import Path

def process_files(file_list):
    for file in file_list:
        if file.endswith(".txt") == True:
            with open(file, "r") as f:
                data = f.read()
                if data != "":
                    print(data)
        else:
            continue

def main():
    files = os.listdir(".")
    process_files(files)

if __name__ == "__main__":
    main()