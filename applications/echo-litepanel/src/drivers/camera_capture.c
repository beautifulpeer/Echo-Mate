/* RV1106 VI -> MJPEG, using the SDK's Rockchip MPI and ISP interfaces. */
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>
#include "sample_comm.h"

static volatile sig_atomic_t quitting;
static void stop(int sig) { (void)sig; quitting = 1; }

int main(void) {
    int result = 1, isp = 0, sys = 0, dev = 0, vi = 0, venc = 0, recv = 0, bound = 0;
    const int width = 480, height = 272, fps = 20;
    VI_DEV_ATTR_S device = {0};
    VI_DEV_BIND_PIPE_S pipe = {0};
    VI_CHN_ATTR_S input = {0};
    VENC_CHN_ATTR_S encoder = {0};
    VENC_RECV_PIC_PARAM_S receive = {0};
    MPP_CHN_S source = {RK_ID_VI, 0, 0};
    MPP_CHN_S destination = {RK_ID_VENC, 0, 0};
    signal(SIGINT, stop);
    signal(SIGTERM, stop);
    mkdir("/tmp/echo-litepanel", 0755);
    unlink("/tmp/echo-litepanel/frame.jpg");

    if (SAMPLE_COMM_ISP_Init(0, RK_AIQ_WORKING_MODE_NORMAL, RK_FALSE, "/etc/iqfiles")) goto cleanup;
    isp = 1;
    if (SAMPLE_COMM_ISP_Run(0)) goto cleanup;
    if (RK_MPI_SYS_Init()) goto cleanup;
    sys = 1;
    int rc = RK_MPI_VI_GetDevAttr(0, &device);
    if (rc == RK_ERR_VI_NOT_CONFIG) {
        if (RK_MPI_VI_SetDevAttr(0, &device)) goto cleanup;
    } else if (rc != RK_SUCCESS) goto cleanup;
    if (RK_MPI_VI_EnableDev(0)) goto cleanup;
    dev = 1;
    pipe.u32Num = 1;
    pipe.PipeId[0] = 0;
    if (RK_MPI_VI_SetDevBindPipe(0, &pipe)) goto cleanup;
    input.stIspOpt.u32BufCount = 3;
    input.stIspOpt.enMemoryType = VI_V4L2_MEMORY_TYPE_DMABUF;
    input.stSize.u32Width = width;
    input.stSize.u32Height = height;
    input.enPixelFormat = RK_FMT_YUV420SP;
    input.enCompressMode = COMPRESS_MODE_NONE;
    input.u32Depth = 0;
    input.stFrameRate.s32SrcFrameRate = -1;
    input.stFrameRate.s32DstFrameRate = fps;
    if (RK_MPI_VI_SetChnAttr(0, 0, &input) || RK_MPI_VI_EnableChn(0, 0)) goto cleanup;
    vi = 1;
    encoder.stVencAttr.enType = RK_VIDEO_ID_MJPEG;
    encoder.stVencAttr.enPixelFormat = RK_FMT_YUV420SP;
    encoder.stVencAttr.u32PicWidth = width;
    encoder.stVencAttr.u32PicHeight = height;
    encoder.stVencAttr.u32VirWidth = width;
    encoder.stVencAttr.u32VirHeight = height;
    encoder.stVencAttr.u32StreamBufCnt = 2;
    encoder.stVencAttr.u32BufSize = 512 * 1024;
    encoder.stRcAttr.enRcMode = VENC_RC_MODE_MJPEGFIXQP;
    encoder.stRcAttr.stMjpegFixQp.u32Qfactor = 45;
    encoder.stRcAttr.stMjpegFixQp.u32SrcFrameRateNum = fps;
    encoder.stRcAttr.stMjpegFixQp.u32SrcFrameRateDen = 1;
    encoder.stRcAttr.stMjpegFixQp.fr32DstFrameRateNum = fps;
    encoder.stRcAttr.stMjpegFixQp.fr32DstFrameRateDen = 1;
    if (RK_MPI_VENC_CreateChn(0, &encoder)) goto cleanup;
    venc = 1;
    receive.s32RecvPicNum = -1;
    if (RK_MPI_VENC_StartRecvFrame(0, &receive)) goto cleanup;
    recv = 1;
    if (RK_MPI_SYS_Bind(&source, &destination)) goto cleanup;
    bound = 1;
    int failures = 0;
    while (!quitting) {
        VENC_PACK_S pack = {0};
        VENC_STREAM_S frame = {0};
        frame.pstPack = &pack;
        frame.u32PackCount = 1;
        if (RK_MPI_VENC_GetStream(0, &frame, 1000)) {
            if (++failures >= 10) goto cleanup;
            continue;
        }
        failures = 0;
        const unsigned char *data = RK_MPI_MB_Handle2VirAddr(pack.pMbBlk);
        /* RV1106's MB mapping already starts at the valid ring-buffer packet,
         * as in the SDK samples. u32Offset is the ring position, not an
         * additional offset into this mapped pointer. */
        if (data && pack.u32Len && pack.u32Len <= 512 * 1024) {
            size_t length = pack.u32Len;
            FILE *file = fopen("/tmp/echo-litepanel/frame.tmp", "wb");
            if (file) {
                size_t written = fwrite(data, 1, length, file);
                int closed = fclose(file);
                if (written == length && !closed)
                    rename("/tmp/echo-litepanel/frame.tmp", "/tmp/echo-litepanel/frame.jpg");
            }
        }
        RK_MPI_VENC_ReleaseStream(0, &frame);
    }
    result = 0;
cleanup:
    unlink("/tmp/echo-litepanel/frame.jpg");
    if (bound) RK_MPI_SYS_UnBind(&source, &destination);
    if (recv) RK_MPI_VENC_StopRecvFrame(0);
    if (venc) RK_MPI_VENC_DestroyChn(0);
    if (vi) RK_MPI_VI_DisableChn(0, 0);
    if (dev) RK_MPI_VI_DisableDev(0);
    if (sys) RK_MPI_SYS_Exit();
    if (isp) SAMPLE_COMM_ISP_Stop(0);
    if (result) fprintf(stderr, "echo-camera: ISP/VI/MJPEG failed; check sensor and IQ files\n");
    return result;
}
