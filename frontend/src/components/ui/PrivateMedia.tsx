/**
 * 带 media_token 自动刷新的 img / video 包装。
 *
 * @author wanghaobo
 */

import { useCallback, useRef, useState, type ImgHTMLAttributes, type SyntheticEvent, type VideoHTMLAttributes } from "react";
import { isPrivateMediaUrl, refreshMediaUrl } from "@/lib/mediaUrl";

function PrivateMediaImgInner({
  src,
  onError,
  ...rest
}: ImgHTMLAttributes<HTMLImageElement>) {
  const [activeSrc, setActiveSrc] = useState<string | undefined>(
    typeof src === "string" ? src : undefined,
  );
  const retryCountRef = useRef(0);

  const onMediaError = useCallback(
    (event: SyntheticEvent<HTMLImageElement, Event>) => {
      const original = typeof src === "string" ? src : null;
      if (original && isPrivateMediaUrl(original) && retryCountRef.current < 2) {
        retryCountRef.current += 1;
        void refreshMediaUrl(original).then((refreshed) => {
          if (refreshed) setActiveSrc(refreshed);
        });
      }
      onError?.(event);
    },
    [onError, src],
  );

  return (
    <img
      {...rest}
      src={activeSrc}
      alt={rest.alt ?? ""}
      onError={onMediaError}
    />
  );
}

function PrivateMediaVideoInner({
  src,
  onError,
  ...rest
}: VideoHTMLAttributes<HTMLVideoElement>) {
  const [activeSrc, setActiveSrc] = useState<string | undefined>(
    typeof src === "string" ? src : undefined,
  );
  const retryCountRef = useRef(0);

  const onMediaError = useCallback(
    (event: SyntheticEvent<HTMLVideoElement, Event>) => {
      const original = typeof src === "string" ? src : null;
      if (original && isPrivateMediaUrl(original) && retryCountRef.current < 2) {
        retryCountRef.current += 1;
        void refreshMediaUrl(original).then((refreshed) => {
          if (refreshed) setActiveSrc(refreshed);
        });
      }
      onError?.(event);
    },
    [onError, src],
  );

  return (
    // eslint-disable-next-line jsx-a11y/media-has-caption -- 生成式预览视频通常无字幕源
    <video
      {...rest}
      src={activeSrc}
      onError={onMediaError}
    />
  );
}

export function PrivateMediaImg(props: ImgHTMLAttributes<HTMLImageElement>) {
  return <PrivateMediaImgInner key={props.src} {...props} />;
}

export function PrivateMediaVideo(props: VideoHTMLAttributes<HTMLVideoElement>) {
  return <PrivateMediaVideoInner key={props.src} {...props} />;
}
