import json

def pretty_json_dump(data, f):
    json.dump(
        data,
        f,
        sort_keys=True,
        indent=4, 
        separators=(',', ': '))

    f.write("\n")

def pretty_json_dumps(data):
    return json.dumps(
            data,
            sort_keys=True,
            indent=4, 
            separators=(',', ': ')) + "\n"
