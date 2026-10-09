from __future__ import annotations
from pathlib import Path
import math
import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'assets' / 'style_reference_koi.png'
OUT = ROOT / 'assets' / 'fish'
KINDS = ('koi','goldfish','neon','betta')
FRAMES = 16


def extract_sprite(img: np.ndarray) -> np.ndarray:
    # The style reference has a cyan water background and a pearl-white/vermilion fish.
    # A red-channel matte is more stable than GrabCut here and avoids baking water into the sprite.
    b,g,r=cv2.split(img)
    H,W=r.shape; yy,xx=np.ogrid[:H,:W]
    roi=(xx>W*.30)&(xx<W*.67)&(yy<H*.96)
    seed=roi & (r>182) & ((r-g>10)|(r>215))
    matte=seed.astype(np.uint8)*255
    matte=cv2.morphologyEx(matte,cv2.MORPH_CLOSE,cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(11,11)),iterations=2)
    matte=cv2.dilate(matte,cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(7,7)),iterations=1)
    n,labels,stats,_=cv2.connectedComponentsWithStats(matte,8)
    final=np.zeros_like(matte); cx=W//2
    for i in range(1,n):
        x,y,w,hh,area=stats[i]
        if area>1000 and x<cx+100 and x+w>cx-100:
            final[labels==i]=255
    alpha=cv2.GaussianBlur(final,(0,0),.9)
    rgba=cv2.cvtColor(img,cv2.COLOR_BGR2BGRA); rgba[:,:,3]=alpha
    rgba[alpha < 6, :3] = 0
    ys,xs=np.where(final>0); pad=12
    x0=max(0,int(xs.min())-pad); x1=min(W,int(xs.max())+pad+1)
    y0=max(0,int(ys.min())-pad); y1=min(H,int(ys.max())+pad+1)
    sprite=rgba[y0:y1,x0:x1]
    return cv2.rotate(sprite, cv2.ROTATE_90_COUNTERCLOCKWISE)


def recolor(rgba: np.ndarray, kind: str) -> np.ndarray:
    if kind == 'koi':
        return rgba.copy()
    out = rgba.copy()
    bgr = out[:,:,:3]
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    H,S,V = cv2.split(hsv)
    alpha = out[:,:,3]
    fg = alpha > 8
    warm = fg & (((H < 28) | (H > 170)) & (S > 65))
    pale = fg & ~warm
    # target BGR colors; luminance/detail is retained by multiplicative shading.
    if kind == 'goldfish':
        c_warm=np.array([28,132,245],np.float32); c_pale=np.array([150,215,255],np.float32)
    elif kind == 'neon':
        c_warm=np.array([170,65,235],np.float32); c_pale=np.array([225,205,70],np.float32)
    else: # betta
        c_warm=np.array([155,55,155],np.float32); c_pale=np.array([225,175,235],np.float32)
    gray=cv2.cvtColor(bgr,cv2.COLOR_BGR2GRAY).astype(np.float32)/210.0
    gray=np.clip(gray,.28,1.18)[...,None]
    arr=bgr.astype(np.float32)
    arr[warm]=c_warm*gray[warm]
    arr[pale]=c_pale*gray[pale]
    # preserve dark ink/eye details
    dark=(cv2.cvtColor(bgr,cv2.COLOR_BGR2GRAY)<72)&fg
    arr[dark]=bgr[dark]
    out[:,:,:3]=np.clip(arr,0,255).astype(np.uint8)
    return out


def warp_frame(src: np.ndarray, phase: float) -> np.ndarray:
    # Transparent padding prevents the tail from being clipped while it swings.
    h,w=src.shape[:2]
    pad_y=max(28,int(h*.16)); pad_x=8
    canvas=np.zeros((h+2*pad_y,w+2*pad_x,4),np.uint8)
    canvas[pad_y:pad_y+h,pad_x:pad_x+w]=src
    H,W=canvas.shape[:2]
    yy,xx=np.indices((H,W),dtype=np.float32)
    # x=tail(left) -> head(right). Head stays almost rigid; tail receives largest amplitude.
    s=np.clip((xx-pad_x)/max(1,w-1),0,1)
    tail_env=(1-s)**2.35
    mid_env=np.exp(-((s-.40)/.28)**2)*.28
    amp=(pad_y*.62)*tail_env + (pad_y*.16)*mid_env
    # travelling body wave; strongest at tail, almost zero at head
    disp=amp*np.sin(phase + s*math.pi*1.35)
    # subtle forward/back tail compression gives a less mechanical pendulum feel
    xdisp=(pad_x*.45 + 2.0)*tail_env*np.cos(phase + s*math.pi)
    map_x=xx-xdisp
    map_y=yy-disp
    return cv2.remap(canvas,map_x,map_y,cv2.INTER_CUBIC,borderMode=cv2.BORDER_CONSTANT,borderValue=(0,0,0,0))


def main():
    img=cv2.imread(str(SRC),cv2.IMREAD_COLOR)
    if img is None: raise SystemExit(f'cannot read {SRC}')
    base=extract_sprite(img)
    OUT.mkdir(parents=True,exist_ok=True)
    for kind in KINDS:
        kd=OUT/kind; kd.mkdir(exist_ok=True)
        colored=recolor(base,kind)
        for i in range(FRAMES):
            phase=2*math.pi*i/FRAMES
            cv2.imwrite(str(kd/f'{i:02d}.png'),warp_frame(colored,phase))
    print(f'generated {FRAMES} frames x {len(KINDS)} kinds in {OUT}')

if __name__=='__main__': main()
