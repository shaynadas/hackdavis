"""
probe_camera.py — find your USB webcam on the Pi and see what it sees

Lists every /dev/video* device, asks v4l2 what it is and what formats
it supports, then tries an actual MJPG capture through OpenCV.

Saves a JPEG snapshot from every device that successfully grabs a frame,
so you can confirm the camera sees the right thing even over SSH.

Run on the Pi:
    sudo apt install -y v4l-utils
    python probe_camera.py              # snapshots only, headless safe
    python probe_camera.py --live       # also pop a live preview window

Output goes to ./snapshots/probe_videoN.jpg
"""

import cv2
import os
import re
import subprocess
import sys
import time


SNAP_DIR = 'snapshots'


def list_video_devices():
    if not os.path.isdir('/dev'):
        return []
    devs = []
    for name in sorted(os.listdir('/dev')):
        m = re.fullmatch(r'video(\d+)', name)
        if m:
            devs.append((int(m.group(1)), f'/dev/{name}'))
    return devs


def run(cmd):
    try:
        return subprocess.check_output(
            cmd, stderr=subprocess.DEVNULL, timeout=3
        ).decode(errors='ignore')
    except Exception:
        return ''


def device_info(path):
    out = run(['v4l2-ctl', '--device', path, '--info'])
    name, driver = 'unknown', ''
    for line in out.splitlines():
        s = line.strip()
        if s.startswith('Card type'):
            name = s.split(':', 1)[1].strip()
        elif s.startswith('Driver name'):
            driver = s.split(':', 1)[1].strip()
    return name, driver


def device_formats(path):
    out = run(['v4l2-ctl', '--device', path, '--list-formats-ext'])
    if not out:
        return []
    fmts, current = [], None
    for line in out.splitlines():
        s = line.strip()
        m = re.search(r"\[\d+\]:\s*'(\w+)'", s)
        if m:
            current = m.group(1)
            continue
        m = re.match(r'Size:\s*\w+\s+(\d+x\d+)', s)
        if m and current:
            entry = f'{current} {m.group(1)}'
            if entry not in fmts:
                fmts.append(entry)
    return fmts


def test_capture(idx, fourcc='MJPG', w=640, h=480, warmup=5):
    """
    Try to capture frames. Saves the last good frame to snapshots/probe_videoN.jpg.
    Returns (ok, message, fps_estimate, snapshot_path).
    """
    cap = cv2.VideoCapture(idx, cv2.CAP_V4L2)
    if not cap.isOpened():
        return False, 'cannot open', 0.0, None

    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*fourcc))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, w)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, h)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

    actual_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    actual_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    for _ in range(warmup):
        cap.read()

    n = 20
    last_frame = None
    t0 = time.time()
    grabbed = 0
    for _ in range(n):
        ok, frame = cap.read()
        if ok:
            grabbed += 1
            last_frame = frame
    dt = time.time() - t0
    cap.release()

    if grabbed == 0 or last_frame is None:
        return False, 'opened, no frames', 0.0, None

    fps = grabbed / dt if dt > 0 else 0.0

    os.makedirs(SNAP_DIR, exist_ok=True)
    snap_path = os.path.join(SNAP_DIR, f'probe_video{idx}.jpg')

    # Stamp metadata onto the snapshot so you know which camera it came from
    stamp = last_frame.copy()
    label = f'/dev/video{idx}  {actual_w}x{actual_h}  {fps:.1f} FPS'
    cv2.rectangle(stamp, (0, 0), (stamp.shape[1], 28), (0, 0, 0), -1)
    cv2.putText(stamp, label, (8, 20),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 0), 1)
    cv2.imwrite(snap_path, stamp)

    return True, f'{actual_w}x{actual_h}, {grabbed}/{n} frames', fps, snap_path


def live_preview(idx, fourcc='MJPG', w=640, h=480):
    """Open the camera and show a live window with FPS overlay. q to quit."""
    cap = cv2.VideoCapture(idx, cv2.CAP_V4L2)
    if not cap.isOpened():
        print(f'[live] cannot open /dev/video{idx}')
        return

    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*fourcc))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, w)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, h)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

    print(f'[live] showing /dev/video{idx}, press q in the window to quit')

    fps_t, fps_n, fps = time.time(), 0, 0.0
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                continue

            fps_n += 1
            now = time.time()
            if now - fps_t >= 1.0:
                fps = fps_n / (now - fps_t)
                fps_n = 0
                fps_t = now

            cv2.putText(frame, f'/dev/video{idx}  {fps:.1f} FPS',
                        (10, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
            try:
                cv2.imshow(f'probe video{idx}', frame)
                if (cv2.waitKey(1) & 0xFF) == ord('q'):
                    break
            except cv2.error as e:
                print(f'[live] no display available, falling back to snapshot only')
                print(f'[live] error: {e}')
                break
    finally:
        cap.release()
        try:
            cv2.destroyAllWindows()
        except Exception:
            pass


def main():
    show_live = '--live' in sys.argv

    print('=' * 64)
    print('Pi USB webcam probe')
    print('=' * 64)

    devs = list_video_devices()
    if not devs:
        print('No /dev/video* devices found.')
        print('Run `lsusb` to confirm the webcam is detected by USB.')
        return

    print(f'\nFound {len(devs)} video device(s):\n')

    candidates = []
    for idx, path in devs:
        name, driver = device_info(path)
        print(f'[{idx}] {path}')
        print(f'     name: {name}')
        if driver:
            print(f'     driver: {driver}')

        fmts = device_formats(path)
        if fmts:
            print(f'     formats: {", ".join(fmts[:6])}')
        else:
            print(f'     formats: (none reported, often a metadata node)')

        if fmts:
            ok, msg, fps, snap = test_capture(idx)
            mark = 'OK  ' if ok else 'FAIL'
            print(f'     capture: [{mark}] {msg}' + (f', ~{fps:.1f} FPS' if ok else ''))
            if snap:
                print(f'     snapshot: {snap}')
            if ok:
                candidates.append((idx, name, fps, snap))
        else:
            print(f'     capture: skipped')
        print()

    print('=' * 64)
    if not candidates:
        print('No device successfully captured a frame.')
        print('Check: lsusb shows the webcam, user is in the `video` group,')
        print('       no other process holds the camera, USB has enough power.')
        return

    best = max(candidates, key=lambda c: c[2])
    print(f'Recommended index: {best[0]}  ({best[1]}, ~{best[2]:.1f} FPS)')
    print(f'\nUse it like:')
    print(f'    python cv_pipeline_pi.py {best[0]}')

    print(f'\nSnapshots saved in ./{SNAP_DIR}/')
    print(f'View them on the Pi:')
    print(f'    xdg-open {best[3]}')
    print(f'Or pull them to your laptop:')
    print(f'    scp pi@<pi-ip>:{os.path.abspath(best[3])} .')

    if len(candidates) > 1:
        others = ', '.join(str(c[0]) for c in candidates if c[0] != best[0])
        print(f'\nOther working indices: {others}')

    if show_live:
        print()
        live_preview(best[0])


if __name__ == '__main__':
    main()
