import { Composition } from 'remotion';
import { MyComp } from './Composition';

export const RemotionRoot: React.FC = () => {
  return (
    <>
      <Composition
        id="MyComp"
        component={MyComp}
        durationInFrames={1800}
        fps={30}
        width={1080}
        height={1920}
        defaultProps={{
          videoUrls: ["https://www.w3schools.com/html/mov_bbb.mp4"],
          audioUrl: "https://www.w3schools.com/html/horse.mp3",
          sfxUrls: [],
          bgmUrl: "",
          segments: [
            { start: 0, end: 5, text: "HOOK WITH POP", text_effect: "pop" },
            { start: 5, end: 10, text: "TECH GLITCH TEXT", text_effect: "glitch" },
            { start: 10, end: 60, text: "LORE TYPEWRITER", text_effect: "typewriter" }
          ],
          effects: {
            zoom: true,
            transition: 'flash',
            textStyle: 'bold'
          }
        }}
      />
    </>
  );
};