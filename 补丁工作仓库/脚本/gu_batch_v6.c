/* Freestanding x86 helper. Exact native addresses belong to the supported Steam build.
 * Inventory mutation occurs at the original final-result call. The native
 * driver is entered only after its original ten-step transition completes.
 * No CRT, OS polling, controller reopening, process attachment or save writes.
 */
typedef unsigned int U;
#define D(a) (*(volatile int *)(a))
#define P(a) (*(U *)(a))
#define F(addr,ret,args) ((ret (__cdecl *)args)(addr))
#define EXPORT __declspec(dllexport)
#define MENU 0x531b50
#define STAGE 0x58149c
#define FIRST 0x581518
#define SECOND 0x58151c
#define BUSY 0x581520
#define ANIM 0x531b64
#define ORIG_INPUT F(0x4b4b90,int,(int))
#define ORIG_UPDATE F(0x4c3180,void,(void))
#define RECIPE F(0x4ddf40,int,(int,int))
#define DELTA F(0x4e9630,int,(int,int))
#define SOUND F(0x4f3280,void,(int))
#define CONFIRM F(0x4e0a90,int,(void))
#define REFRESH F(0x4bba50,void,(void))
#define MAX 99
typedef struct { int id,before,after; } Count;
typedef struct {int first,second,n,used,eggsBefore,eggFinal,mixed;int inA[MAX],out[MAX];Count counts[300];} Plan;
/* Keep the first twelve fields stable for existing transaction fixtures. */
typedef struct {int seenA,seenB,quantity,maximum,selected,armed,finished,completed,committed,mouseX,mouseY,active,quantityMenu,resultHeld,resultId,failurePending,previewQuantity,previewItem,previewKinds;} State;
EXPORT State GuState;
static Plan plan;
static int journalId[400],journalDelta[400],journalN;
static int imagesReady,imageIds[8],guDrawActive;
static char resultFormat[256];
static int summaryFormat(int n,char *dst,int capacity);

static int egg(int id) { return id>=D(0x531bec)&&id<D(0x531bec)+D(0x531bf0); }
static int eggCount(int id) {
  int n=0,i; U node=P(0x59a2e8);
  for(i=0;node && i<99;i++,node=P(node+16)) if(P(node+4)&&D(P(node+4))==id)n++;
  return n;
}
EXPORT int GuCount(int id) {
  U obj;int *v;
  if(!id)return 0;
  if(egg(id))return eggCount(id);
  obj=F(0x4dca10,U,(U))(id);if(!obj)return 0;
  v=F(0x4dcc20,int *,(U,U))(P(obj+0x6c),0x14);
  return v&&*v>0?*v:0;
}
static Count *counter(int id) {
  int i;Count *c;
  for(i=0;i<plan.used;i++)if(plan.counts[i].id==id)return &plan.counts[i];
  if(plan.used>=300)return (Count *)0;
  c=&plan.counts[plan.used++];c->id=id;c->before=GuCount(id);c->after=c->before;return c;
}
static int virtualDelta(int id,int delta) {
  Count *c=counter(id);if(!c)return 0;
  if(c->after+delta<0)return 0;
  c->after+=delta;
  if(egg(id))plan.eggFinal+=delta;
  return c->after<=99 && plan.eggFinal<=99;
}
/* Returns the valid prefix. The held first recipe is already outside inventory. */
EXPORT int GuBuild(int wanted) {
  int a=D(FIRST),b=D(SECOND),top=99,i,j,r,available[99],availableN=0;
  U node;
  plan.first=a;plan.second=b;plan.n=0;plan.used=0;plan.mixed=0;
  plan.eggsBefore=D(0x59a2ec);plan.eggFinal=plan.eggsBefore;
  if(!a || wanted<1)return 0;
  if(wanted>99)wanted=99;
  if(egg(a)) {
    /* Native egg IDs retain their individual result mapping. */
    node=P(0x59a2e8);
    for(i=0;node&&i<99;i++,node=P(node+16))
      if(P(node+4))available[availableN++]=D(P(node+4));
    top=availableN+1;
    if(b && egg(b))top=1; /* unreachable in the new single-egg selection flow */
    else if(b && top>GuCount(b)+1)top=GuCount(b)+1;
  } else {
    if(!b)return 0;
    if(a==b)top=(GuCount(a)+2)/2;
    else {top=GuCount(a)+1;if(top>GuCount(b)+1)top=GuCount(b)+1;}
  }
  if(top>wanted)top=wanted;
  for(i=0;i<top;i++) {
    j=i&&egg(a)?available[i-1]:a;
    r=RECIPE(j,b);if(r<=0||r==(int)0xffffffff)break;
    plan.inA[i]=j;plan.out[i]=r;
    /* The native popup destination is one 256-byte row. Never commit a batch
     * whose complete, per-product result cannot be represented safely. */
    if(!summaryFormat(i+1,resultFormat,sizeof(resultFormat)))break;
    if(i) {
      if(!virtualDelta(j,-1))break;
      if(b&&!virtualDelta(b,-1))break;
    }
    if(!virtualDelta(r,1))break;
    if(i&&r!=plan.out[0])plan.mixed=1;
    plan.n=i+1;
  }
  return plan.n;
}
static void consumeConfirm(void) {
  int i,slots[6]={0,1,12,15,21,22}; U p;
  for(i=0;i<6;i++){p=0x580c94+20*slots[i];*(unsigned char *)p=0;D(p+8)=0;}
  D(0x59a3ac)=0;D(0x59a334)=0;*(unsigned char *)0x580dc0=0;
}
static void synchronize(void) {
  int a=D(FIRST),b=D(SECOND);
  if(GuState.armed||D(BUSY))return;
  if(!GuState.active||a!=GuState.seenA||b!=GuState.seenB) {
    GuState.active=1;GuState.seenA=a;GuState.seenB=b;GuState.finished=0;
    GuState.maximum=GuBuild(99);GuState.quantity=GuState.maximum?1:0;
    GuState.previewQuantity=-1;
    /* Quantity appears only when there is a valid, storable result: never00. */
    GuState.quantityMenu=GuState.maximum>0;
    if(a!=GuState.resultId)GuState.resultHeld=0;
    GuState.selected=GuState.maximum?1:0;
    GuState.mouseX=D(0x53b8c0);GuState.mouseY=D(0x53b8c4);
  }
}
/* Result-name preview data only. Original material sprites remain untouched. */
EXPORT int __cdecl GuPreview(int *item,int *quantity,int *kinds) {
  int i,j,unique=0;
  *item=0;*quantity=0;*kinds=0;
  if(D(MENU)!=10||D(STAGE)<3||D(BUSY)||GuState.armed||!F(0x4cb690,int,(int))(1))return 0;
  synchronize();
  if(GuState.finished||!GuState.quantityMenu||GuState.quantity<1)return 0;
  if(GuState.previewQuantity!=GuState.quantity) {
    if(GuBuild(GuState.quantity)!=GuState.quantity)return 0;
    for(i=0;i<plan.n;i++) {
      for(j=0;j<i&&plan.out[j]!=plan.out[i];j++);
      if(j==i)unique++;
    }
    GuState.previewItem=plan.out[0];GuState.previewKinds=unique;
    GuState.previewQuantity=GuState.quantity;
  }
  *item=GuState.previewItem;*quantity=GuState.quantity;*kinds=GuState.previewKinds;return 1;
}
static int mutate(int id,int delta) {
  int before=GuCount(id);DELTA(id,delta);
  if(GuCount(id)!=before+delta)return 0;
  journalId[journalN]=id;journalDelta[journalN++]=delta;return 1;
}
EXPORT int GuCommit(void) {
  int i;
  if(plan.n!=GuState.quantity||plan.n<1||D(FIRST)!=plan.first||D(SECOND)!=plan.second)return 0;
  if(D(0x59a2ec)!=plan.eggsBefore)return 0;
  for(i=0;i<plan.used;i++)if(GuCount(plan.counts[i].id)!=plan.counts[i].before)return 0;
  journalN=0;
  for(i=1;i<plan.n;i++) {
    if(!mutate(plan.inA[i],-1))goto rollback;
    if(plan.second&&!mutate(plan.second,-1))goto rollback;
  }
  /* First result stays in the original held slot; native B/back adds it once. */
  for(i=1;i<plan.n;i++)if(!mutate(plan.out[i],1))goto rollback;
  GuState.committed=1;GuState.completed=plan.n;return 1;
rollback:
  while(journalN){journalN--;DELTA(journalId[journalN],-journalDelta[journalN]);}
  GuState.committed=0;return 0;
}
EXPORT int __cdecl GuFinish(int a,int b) {
  if(GuState.armed && a==plan.first && b==plan.second) {
    if(!GuState.committed && !GuCommit()) {
      D(BUSY)=0;D(ANIM)=10;GuState.armed=0;GuState.active=0;
      GuState.failurePending=1;
      consumeConfirm();SOUND(9);return 0;
    }
    return plan.out[0];
  }
  return RECIPE(a,b);
}
/* Only the verified 004c3521 call uses this gate. On a failed transaction, skip
 * the original result-slot overwrite, popup and B-slot clearing via its own
 * epilogue. Native EBP/stack and both held ingredients remain intact.
 */
EXPORT __declspec(naked) int __cdecl GuFinishGate(int a,int b) {
  __asm {
    mov eax,[esp+8]
    push eax
    mov eax,[esp+8]
    push eax
    call GuFinish
    add esp,8
    test eax,eax
    jnz finish_return
    cmp dword ptr [esp],4c3526h
    jne finish_return
    mov dword ptr [esp],4c35e5h
  finish_return:
    ret
  }
}
static char *itemName(int id) {
  U group=F(0x4f8450,U,(U))(0x7f100000),record;
  /* This is a zero-based group INDEX, not a pointer. Native -1 is invalid. */
  if(group==(U)-1)return (char *)0;
  record=F(0x4f85b0,U,(U,int))(group,id);
  return record?F(0x4dddb0,char *,(U,U))(record,0x7ff2f000):(char *)0;
}
static int putByte(char *dst,int *used,int cap,char value) {
  if(*used>=cap-1)return 0;
  dst[(*used)++]=value;dst[*used]=0;return 1;
}
/* Retain the native localized prefix, color controls and suffix around %s.
 * Item names are literal data, so '%' must be escaped for native sprintf.
 * Native gitem names/UI strings use Big5; the added punctuation/unit matches it.
 * The formatted string is no longer than the checked format itself. */
static int summaryFormat(int n,char *dst,int capacity) {
  char *fmt=F(0x4fb390,char *,(int))(0x7e0),*name;
  int ids[MAX],counts[MAX],used=0,groups=0,i,j,k,marker=-1,end;
  dst[0]=0;
  if(!fmt||n<1||n>MAX)return 0;
  for(i=0;i<128&&fmt[i];i++) {
    if(fmt[i]=='%') {
      if(fmt[i+1]=='%'){i++;continue;}
      if(fmt[i+1]=='s'&&marker<0){marker=i;i++;continue;}
      return 0; /* Do not guess varargs for an unknown format. */
    }
  }
  if(i>=128||marker<0)return 0;end=i;
  for(i=0;i<marker;i++)if(!putByte(dst,&used,capacity,fmt[i]))return 0;
  for(i=0;i<n;i++) {
    for(j=0;j<groups&&ids[j]!=plan.out[i];j++);
    if(j==groups){ids[groups]=plan.out[i];counts[groups++]=0;}
    counts[j]++;
  }
  for(i=0;i<groups;i++) {
    if(i) {
      if(!putByte(dst,&used,capacity,(char)0xa1)||!putByte(dst,&used,capacity,(char)0x42))return 0;
    }
    name=itemName(ids[i]);if(!name||!name[0])return 0;
    for(k=0;k<64&&name[k];k++) {
      if(!putByte(dst,&used,capacity,name[k]))return 0;
      if(name[k]=='%'&&!putByte(dst,&used,capacity,'%'))return 0;
    }
    if(k>=64)return 0;
    if(!putByte(dst,&used,capacity,' '))return 0;
    /* Big5 multiplication sign; no selected quantity appears in the preview. */
    if(!putByte(dst,&used,capacity,(char)0xa1)||!putByte(dst,&used,capacity,(char)0xd1))return 0;
    if(counts[i]>=10&&!putByte(dst,&used,capacity,(char)('0'+counts[i]/10)))return 0;
    if(!putByte(dst,&used,capacity,(char)('0'+counts[i]%10)))return 0;
  }
  for(i=marker+2;i<end;i++)if(!putByte(dst,&used,capacity,fmt[i]))return 0;
  return 1;
}
EXPORT char *__cdecl GuFormat(int id) {
  char *src=F(0x4fb390,char *,(int))(id);
  if(!GuState.committed||GuState.completed<1)return src;
  if(!summaryFormat(GuState.completed,resultFormat,sizeof(resultFormat)))return src;
  return resultFormat;
}
static void completed(void) {
  if(GuState.committed&&!D(BUSY)) {
    GuState.armed=0;GuState.committed=0;GuState.finished=1;
    GuState.seenA=D(FIRST);GuState.seenB=D(SECOND);GuState.quantity=0;
    GuState.maximum=0;GuState.selected=0;GuState.quantityMenu=0;
    GuState.resultHeld=1;GuState.resultId=D(FIRST);
  }
}
static void failureMessage(void) {
  if(GuState.failurePending&&D(MENU)==10&&!D(BUSY)&&F(0x4cb690,int,(int))(1)) {
    GuState.failurePending=0;consumeConfirm();F(0x4cb710,int,(int))(0x1f4a);
  }
}
EXPORT void __cdecl GuUpdate(void) {
  if(D(MENU)!=10){ORIG_UPDATE();return;}
  completed();
  failureMessage();
  synchronize();
  if(D(BUSY)&&D(ANIM)>0) {
    U obj;int id;
    /* Native refresh hides layer0 before this call. Preserve its material
     * visibility setup while deferring only the premature result settlement.
     * Leave position and effect bit13 to native004b7b70. */
    for(id=0x642;id<=0x643;id++) {
      if(id==0x643&&!D(SECOND))continue;
      obj=F(0x4e4a70,U,(int,int))(0,id);
      if(obj)F(0x4ccdc0,void,(U,int))(obj+0x28,0);
    }
    return;
  }
  if(D(BUSY)||!GuState.armed)consumeConfirm();
  else D(0x581498)=1;
  ORIG_UPDATE();
  if(D(BUSY))consumeConfirm();
  completed();
  failureMessage();
  if(!D(BUSY))GuState.armed=0;
}
static int rowAt(int x,int y) {
  if(x<18||x>202)return -1;
  if(!GuState.quantityMenu) {
    if(y>=364&&y<403)return 0;
    if(y>=403&&y<446)return 2;
    return -1;
  }
  if(y>=347&&y<384)return 0;
  if(y>=384&&y<419)return 1;
  if(y>=419&&y<460)return 2;
  return -1;
}
/* Two-row mode skips quantity; hit rectangles follow the user PNG layout. */
static int nextRow(int selected,int step) {
  if(!GuState.quantityMenu)return selected==0?2:0;
  return (selected+step+3)%3;
}
EXPORT int __cdecl GuInput(int mode) {
  int up,down,left,right,confirm,row,old,x,y,clicked=0;
  if(mode!=10||D(MENU)!=10)return ORIG_INPUT(mode);
  if(D(STAGE)<3) {
    /* Empty first-entry stage0 otherwise burns one confirmation moving to1,
     * with identical visuals. The populated list is already ready to select.
     * Prepare focus only; native input/confirmation/button/consumption remain. */
    if(D(STAGE)==0&&!D(FIRST)&&!D(SECOND)&&!D(BUSY)&&D(0x581540)>0
       &&F(0x4cb690,int,(int))(1))D(STAGE)=1;
    return ORIG_INPUT(mode);
  }
  if(D(BUSY))return 0;
  failureMessage();
  if(!F(0x4cb690,int,(int))(1))return 0;
  if(GuState.finished&&F(0x4cb690,int,(int))(1))GuState.active=0;
  synchronize();old=GuState.selected;
  up=F(0x4e1e80,int,(void))();down=F(0x4e0c90,int,(void))();
  left=F(0x4e1740,int,(void))();right=F(0x4e1bc0,int,(void))();confirm=CONFIRM();
  if(up){GuState.selected=nextRow(GuState.selected,-1);SOUND(8);}
  if(down){GuState.selected=nextRow(GuState.selected,1);SOUND(8);}
  x=D(0x53b8c0);y=D(0x53b8c4);row=rowAt(x,y);
  if(D(0x580c88)==2 && (x!=GuState.mouseX||y!=GuState.mouseY) && row>=0)GuState.selected=row;
  GuState.mouseX=x;GuState.mouseY=y;
  if(*(unsigned char *)0x580dc0==2 && row>=0) {
    GuState.selected=row;clicked=1;
    if(row==1){left=x>=100&&x<121;right=x>=151&&x<174;confirm=0;}
    else confirm=1;
    *(unsigned char *)0x580dc0=0;
  }
  if(GuState.quantityMenu && GuState.selected==1 && GuState.maximum>0 && (left||right)) {
    GuState.quantity+=right-left;
    if(GuState.quantity<1)GuState.quantity=1;
    if(GuState.quantity>GuState.maximum)GuState.quantity=GuState.maximum;
    SOUND(8);
  }
  if(confirm && F(0x4cb690,int,(int))(1)) {
    if(GuState.selected==0) {
      /* Replacing a ready recipe returns every held ingredient first. */
      if(GuState.resultHeld||GuState.finished||GuState.maximum>0||D(SECOND)) {
        if(D(FIRST))DELTA(D(FIRST),1);if(D(SECOND))DELTA(D(SECOND),1);
        D(FIRST)=0;D(SECOND)=0;
      }
      D(STAGE)=D(FIRST)?1:0;D(0x581498)=0;
      GuState.active=0;GuState.quantity=0;GuState.finished=0;
      GuState.resultHeld=0;
      consumeConfirm();SOUND(4);return 1;
    }
    if(GuState.selected==2) {
      if(GuState.quantity>0 && GuBuild(GuState.quantity)==GuState.quantity) {
        GuState.armed=1;GuState.committed=0;GuState.completed=0;
        D(STAGE)=4;D(0x581498)=1;D(ANIM)=10;
        /* Let native004b7b70 advance all original positions/effects. The next
         * refresh must not commit immediately just because confirm is held. */
        D(BUSY)=1;consumeConfirm();SOUND(4);return 1;
      }
      /* Reuse the native invalid-recipe message, with the current input consumed
       * before entering its script so the same press cannot dismiss it. */
      consumeConfirm();SOUND(9);F(0x4cb710,int,(int))(0x1f4a);
    }
    consumeConfirm();
  }
  return old!=GuState.selected||left||right||up||down||clicked;
}
static void hideOldButtons(void) {
  U obj;int id;
  for(id=0x640;id<=0x641;id++){
    obj=F(0x4e4a70,U,(int,int))(0,id);
    if(obj)F(0x4cce10,void,(U,int))(obj+0x28,0);
  }
}
static int imageAdd(char *name) {
  int result;
  __asm {
    push 1
    mov eax,name
    push eax
    push 0
    mov ecx,570b38h
    mov eax,4af910h
    call eax
    mov result,eax
  }
  return result;
}
static void imageDraw(int index,int x,int y) {
  __asm {
    push y
    push x
    push 0
    push index
    mov ecx,570b38h
    mov eax,4afa10h
    call eax
  }
}
static void nameDraw(char *name,int x,int y) {
  int color=F(0x48e4d0,int,(int,int,int))(9,6,3);
  int outline=F(0x48e4d0,int,(int,int,int))(26,24,20);
  int surface=D(0x5997e8);
  __asm {
    push outline
    mov ecx,57fe60h
    mov eax,4a4830h
    call eax
    push 4
    push color
    push name
    push y
    push x
    push surface
    mov ecx,57fe60h
    mov eax,4a4960h
    call eax
  }
}
static void nativeIdleStart(void) {
  U obj;
  /* The native transition starts at40/360 and ends at200. Its own refresh
   * resets the first slot to the single-item center200 even with two slots;
   * restore only that existing two-slot start, never animate/relocate sprites. */
  if(D(SECOND)&&!D(BUSY)&&!GuState.armed) {
    obj=F(0x4e4a70,U,(int,int))(0,0x642);
    if(obj)D(obj+8)=40;
  }
}
EXPORT void __cdecl GuDraw(void) {
  if(D(MENU)==10&&D(STAGE)>=3){hideOldButtons();nativeIdleStart();}
  if(D(MENU)!=10){GuState.active=0;GuState.armed=0;GuState.resultHeld=0;GuState.failurePending=0;}
  guDrawActive++;
  F(0x4e3370,void,(void))();
  guDrawActive--;
}
static void guOverlay(void) {
  int q,selected,item,n,kinds,width,i;char digits[3],*name;
  if(D(MENU)!=10||D(STAGE)<3)return;
  /* No new menu/connector/nameplate may cover the original synthesis effect. */
  if(D(BUSY)||GuState.armed)return;
  synchronize();
  if(!imagesReady) {
    imageIds[0]=imageAdd("np_gu_menu_2_add_v2.png");
    imageIds[1]=imageAdd("np_gu_menu_2_craft_v2.png");
    imageIds[2]=imageAdd("np_gu_menu_3_add_v2.png");
    imageIds[3]=imageAdd("np_gu_menu_3_quantity_v2.png");
    imageIds[4]=imageAdd("np_gu_menu_3_craft_v2.png");
    imageIds[5]=imageAdd("np_gu_preview_name_v3.png");
    imageIds[6]=imageAdd("np_gu_preview_pair_v3.png");
    imageIds[7]=imageAdd("np_gu_preview_single_v3.png");imagesReady=1;
  }
  selected=GuState.quantityMenu?2+GuState.selected:(GuState.selected==2?1:0);
  imageDraw(imageIds[selected],2,324);
  if(GuState.quantityMenu) {
    q=GuState.quantity;digits[0]=(char)('0'+q/10);digits[1]=(char)('0'+q%10);digits[2]=0;
    /* Same native text path as shop quantities; latest user request: no glow. */
    F(0x4c7f50,void,(char *,int,int,int))(digits,0x4a,124,389);
  }
  if(GuPreview(&item,&n,&kinds)) {
    /* Approved layout anchored on the native reference, with no sprite writes. */
    imageDraw(imageIds[D(SECOND)?6:7],0,0);
    imageDraw(imageIds[5],258,334);
    name=kinds>1?"\xa6\x68\xba\xd8\xa6\xa8\xab\x7e":itemName(item);
    if(name) {
      width=0;
      for(i=0;name[i]&&i<64;i++) {
        if((unsigned char)name[i]>=0x80&&name[i+1]){width+=18;i++;}
        else width+=9;
      }
      if(width<=90)nameDraw(name,318-width/2,346);
    }
  }
}
/* Replace the ONE native cursor call inside004e3370. UI is below cursor;
 * its update/draw executes once, retaining native hiding/shape/position logic. */
EXPORT void __cdecl GuCursor(void) {
  if(guDrawActive)guOverlay();
  F(0x474850,void,(void))();
}
void __cdecl GuEntry(void) {}
