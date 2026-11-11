def remov_daplicetes(s):
    t = ''
    for i in s:
        if i not in t:
            t += i
    return t
