import browser_cookie3
from http.cookiejar import Cookie
import io
import sys
import traceback
import typing


SUPPORTED_BROWSERS = {
    "chrome": browser_cookie3.chrome,
    "firefox": browser_cookie3.firefox,
    "edge": browser_cookie3.edge,
    "opera": browser_cookie3.opera
}

def toText(value) -> str:
    if value:
        return "TRUE"
    else:
        return "FALSE"

def cookieToTextRow(cookie: Cookie) -> str:
    fields = (
        cookie.domain,
        toText(cookie.domain_specified),
        cookie.path,
        toText(cookie.secure),
        cookie.expires or 0,
        cookie.name,
        cookie.value
    )
    return "\t".join(str(x) for x in fields)

def dumpCookies(domainFilter: str, outFile: typing.Optional[str], browser: str = "chrome") -> typing.Optional[str]:
    if browser not in SUPPORTED_BROWSERS:
        raise Exception("Unknown browser!")

    cookies = SUPPORTED_BROWSERS[browser](domain_name=domainFilter)

    shouldClose = False
    returns = False

    if outFile is None:
        f = io.StringIO()
        returns = True
    elif outFile == "--":
        f = sys.stdout
    else:
        f = open(outFile, "w")
        shouldClose = True

    f.write("# HTTP Cookie File for domains related to %s.\n" % domainFilter)
    f.write("# dumped with cookiedump.py\n")
    f.write("#\n")
    for c in cookies:
        f.write(cookieToTextRow(c))
        f.write("\n")

    if shouldClose:
        f.close()
    elif returns:
        f.seek(0)
        return f.read()

def main():
    if not 1 <= len(sys.argv) <= 3:
        print("invalid arguments")
        exit(-1)
    
    domainFilter = sys.argv[1]
    outFile = sys.argv[2] if len(sys.argv) >= 3 else "cookies.txt"
    
    dumpCookies(domainFilter, outFile)

if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        exit(-1)
