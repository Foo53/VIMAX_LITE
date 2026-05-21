import React from 'react';
import {AbsoluteFill, Series} from 'remotion';
import {ShotScene} from './ShotScene';

export type TimelineShot = {
  shot_id: string;
  order: number;
  image_path?: string | null;
  image_src?: string | null;
  status: string;
  duration_seconds: number;
  caption: string;
  narration: string;
  motion: {
    type: string;
    strength: number;
  };
  transition: {
    type: string;
    duration_seconds: number;
  };
};

export type TimelineManifest = {
  project: string;
  title: string;
  output_mode: string;
  fps: number;
  width: number;
  height: number;
  shots: TimelineShot[];
  audio: Record<string, string | null>;
  todos: string[];
};

export const VimaxTimelineVideo: React.FC<TimelineManifest> = ({title, shots, fps}) => {
  if (!shots || shots.length === 0) {
    return (
      <AbsoluteFill style={{backgroundColor: '#111827', color: 'white', alignItems: 'center', justifyContent: 'center'}}>
        <h1>{title}</h1>
      </AbsoluteFill>
    );
  }

  return (
    <AbsoluteFill style={{backgroundColor: '#05070a'}}>
      <Series>
        {shots.map((shot) => (
          <Series.Sequence key={shot.shot_id} durationInFrames={Math.max(1, Math.ceil(shot.duration_seconds * fps))}>
            <ShotScene shot={shot} title={title} />
          </Series.Sequence>
        ))}
      </Series>
    </AbsoluteFill>
  );
};
