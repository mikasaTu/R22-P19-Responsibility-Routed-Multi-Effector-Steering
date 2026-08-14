from __future__ import annotations

import argparse
from pathlib import Path
import imageio.v2 as imageio
from PIL import Image, ImageDraw


def main():
    p=argparse.ArgumentParser();p.add_argument("--video-dir",type=Path,required=True);p.add_argument("--output",type=Path,required=True);args=p.parse_args()
    videos=sorted(args.video_dir.glob("*.mp4")); rows=[]
    for path in videos:
        frames=imageio.mimread(path); chosen=[frames[0],frames[len(frames)//2],frames[-1]]
        tiles=[]
        for index,frame in enumerate(chosen):
            image=Image.fromarray(frame).resize((320,180)); draw=ImageDraw.Draw(image); draw.rectangle((0,0,319,20),fill=(0,0,0)); draw.text((5,4),f"{path.stem} frame={index+1}/3",fill=(255,255,255));tiles.append(image)
        row=Image.new("RGB",(960,180));
        for index,tile in enumerate(tiles):row.paste(tile,(320*index,0))
        rows.append(row)
    montage=Image.new("RGB",(960,180*len(rows)),(0,0,0))
    for index,row in enumerate(rows):montage.paste(row,(0,180*index))
    args.output.parent.mkdir(parents=True,exist_ok=True);montage.save(args.output)
if __name__=="__main__":main()

