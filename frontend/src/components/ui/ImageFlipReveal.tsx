/**
 * ImageFlipReveal — 图片切换时的 3D 翻转动画；私有媒体 URL 失败时自动续签 media_token。
 *
 * @author wanghaobo
 */

import { useCallback, useRef, useState, type ReactNode } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { isPrivateMediaUrl, refreshMediaUrl } from "@/lib/mediaUrl";

const MAX_MEDIA_TOKEN_RETRIES = 2;

interface ImageFlipRevealProps {
  src: string | null;
  alt: string;
  className?: string;
  fallback?: ReactNode;
  onError?: () => void;
  loading?: "eager" | "lazy";
}

function ImageFlipRevealInner({
  src,
  alt,
  className,
  fallback,
  onError,
  loading,
}: ImageFlipRevealProps) {
  const [activeSrc, setActiveSrc] = useState<string | null>(src);
  const retryCountRef = useRef(0);

  const handleError = useCallback(() => {
    const original = src;
    if (original && isPrivateMediaUrl(original) && retryCountRef.current < MAX_MEDIA_TOKEN_RETRIES) {
      retryCountRef.current += 1;
      void refreshMediaUrl(original).then((refreshed) => {
        if (refreshed) {
          setActiveSrc(refreshed);
          return;
        }
        onError?.();
      });
      return;
    }
    onError?.();
  }, [onError, src]);

  return (
    <div style={{ perspective: 800 }} className="h-full w-full">
      <AnimatePresence mode="wait">
        {activeSrc ? (
          <motion.img
            key={activeSrc}
            src={activeSrc}
            alt={alt}
            loading={loading}
            className={className ?? "h-full w-full object-cover"}
            initial={{ rotateY: 90, opacity: 0 }}
            animate={{ rotateY: 0, opacity: 1 }}
            exit={{ rotateY: -90, opacity: 0 }}
            transition={{ duration: 0.5, ease: "easeInOut" }}
            style={{ backfaceVisibility: "hidden" }}
            onError={handleError}
          />
        ) : (
          <motion.div
            key="fallback"
            className="h-full w-full"
            initial={{ rotateY: 90, opacity: 0 }}
            animate={{ rotateY: 0, opacity: 1 }}
            exit={{ rotateY: -90, opacity: 0 }}
            transition={{ duration: 0.5, ease: "easeInOut" }}
            style={{ backfaceVisibility: "hidden" }}
          >
            {fallback}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

export function ImageFlipReveal(props: ImageFlipRevealProps) {
  return <ImageFlipRevealInner key={props.src ?? "__empty__"} {...props} />;
}
